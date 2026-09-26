"""Generate the checked-in Xcode app and UI-test project using only Python on Windows."""
from pathlib import Path
import hashlib
import plistlib

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "PotPatrol.xcodeproj"
objects = {}


def ident(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()


def add(object_name, isa, **properties):
    key = ident(object_name)
    objects[key] = dict(isa=isa, **properties)
    return key


def render(value, indent=0):
    if isinstance(value, dict):
        rows = ["{"]
        for key, item in value.items():
            rows.append("\t" * (indent + 1) + f"{render(key)} = {render(item, indent + 1)};")
        rows.append("\t" * indent + "}")
        return "\n".join(rows)
    if isinstance(value, list):
        return "(" + ", ".join(render(item, indent) for item in value) + ("," if value else "") + ")"
    text = str(value)
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def configurations(name, settings):
    configs = []
    for mode in ("Debug", "Release"):
        current = settings.copy()
        current.update(SWIFT_OPTIMIZATION_LEVEL="-Onone" if mode == "Debug" else "-O")
        current["SWIFT_ACTIVE_COMPILATION_CONDITIONS"] = "DEBUG $(inherited)" if mode == "Debug" else "$(inherited)"
        if name == "app":
            current["INFOPLIST_FILE"] = f"NativeApp/Info-{mode}.plist"
        configs.append(add(f"{name}-{mode}", "XCBuildConfiguration", name=mode, buildSettings=current))
    return add(f"{name}-configs", "XCConfigurationList", buildConfigurations=configs,
               defaultConfigurationIsVisible="0", defaultConfigurationName="Release")


def source_group(folder):
    files, builds = [], []
    for file in sorted((ROOT / folder).glob("*.swift")):
        ref = add(str(file.relative_to(ROOT)), "PBXFileReference", lastKnownFileType="sourcecode.swift",
                  path=file.name, sourceTree="<group>")
        files.append(ref)
        builds.append(add("build-" + folder + file.name, "PBXBuildFile", fileRef=ref))
    group = add(folder, "PBXGroup", children=files, path=folder, sourceTree="<group>")
    sources = add(folder + "-sources", "PBXSourcesBuildPhase", buildActionMask="2147483647",
                  files=builds, runOnlyForDeploymentPostprocessing="0")
    return group, sources


app_group, app_sources = source_group("NativeApp")
tests_group, tests_sources = source_group("UITests")
app_product = add("app-product", "PBXFileReference", explicitFileType="wrapper.application",
                  path="PotPatrol.app", sourceTree="BUILT_PRODUCTS_DIR")
tests_product = add("tests-product", "PBXFileReference", explicitFileType="wrapper.cfbundle",
                    path="PotPatrolUITests.xctest", sourceTree="BUILT_PRODUCTS_DIR")
products = add("products", "PBXGroup", name="Products", children=[app_product, tests_product], sourceTree="<group>")
root_group = add("root", "PBXGroup", children=[app_group, tests_group, products], sourceTree="<group>")
package = add("package", "XCLocalSwiftPackageReference", relativePath=".")
dependencies, frameworks = [], []
for product in ["PotPatrolCore", "PotPatrolCapture"]:
    dep = add(product, "XCSwiftPackageProductDependency", package=package, productName=product)
    dependencies.append(dep)
    frameworks.append(add(product + "-link", "PBXBuildFile", productRef=dep))
app_frameworks = add("app-frameworks", "PBXFrameworksBuildPhase", buildActionMask="2147483647",
                     files=frameworks, runOnlyForDeploymentPostprocessing="0")
tests_frameworks = add("tests-frameworks", "PBXFrameworksBuildPhase", buildActionMask="2147483647",
                       files=[], runOnlyForDeploymentPostprocessing="0")
common = dict(SWIFT_VERSION="5.0", IPHONEOS_DEPLOYMENT_TARGET="17.0", SDKROOT="iphoneos",
              TARGETED_DEVICE_FAMILY="1", CODE_SIGN_STYLE="Automatic", CLANG_ENABLE_MODULES="YES")
app_settings = dict(common, PRODUCT_NAME="PotPatrol", PRODUCT_BUNDLE_IDENTIFIER="com.potpatrol.app",
                    GENERATE_INFOPLIST_FILE="NO", SUPPORTED_PLATFORMS="iphoneos iphonesimulator",
                    LD_RUNPATH_SEARCH_PATHS=["$(inherited)", "@executable_path/Frameworks"])
test_settings = dict(common, PRODUCT_NAME="$(TARGET_NAME)", PRODUCT_BUNDLE_IDENTIFIER="com.potpatrol.app.uitests",
                     GENERATE_INFOPLIST_FILE="YES", TEST_TARGET_NAME="PotPatrol",
                     LD_RUNPATH_SEARCH_PATHS=["$(inherited)", "@executable_path/Frameworks", "@loader_path/Frameworks"])
app = add("app", "PBXNativeTarget", name="PotPatrol", productName="PotPatrol", productReference=app_product,
          productType="com.apple.product-type.application", buildConfigurationList=configurations("app", app_settings),
          buildPhases=[app_sources, app_frameworks], buildRules=[], dependencies=[], packageProductDependencies=dependencies)
proxy = add("tests-proxy", "PBXContainerItemProxy", containerPortal=ident("project"), proxyType="1",
            remoteGlobalIDString=app, remoteInfo="PotPatrol")
target_dep = add("tests-dependency", "PBXTargetDependency", target=app, targetProxy=proxy)
tests = add("tests", "PBXNativeTarget", name="PotPatrolUITests", productName="PotPatrolUITests",
            productReference=tests_product, productType="com.apple.product-type.bundle.ui-testing",
            buildConfigurationList=configurations("tests", test_settings), buildPhases=[tests_sources, tests_frameworks],
            buildRules=[], dependencies=[target_dep])
project = add("project", "PBXProject", attributes=dict(LastUpgradeCheck="2600",
              TargetAttributes={app: dict(CreatedOnToolsVersion="26.0"), tests: dict(CreatedOnToolsVersion="26.0", TestTargetID=app)}),
              buildConfigurationList=configurations("project", common), compatibilityVersion="Xcode 14.0",
              developmentRegion="en", hasScannedForEncodings="0", knownRegions=["en", "Base"], mainGroup=root_group,
              productRefGroup=products, projectDirPath="", projectRoot="", packageReferences=[package], targets=[app, tests])
PROJECT.mkdir(exist_ok=True)
(PROJECT / "project.pbxproj").write_text("// !$*UTF8*$!\n" + render(dict(archiveVersion="1", classes={}, objectVersion="56",
                                                       objects=objects, rootObject=project)) + "\n", encoding="utf-8")
scheme = PROJECT / "xcshareddata/xcschemes/PotPatrol.xcscheme"
scheme.parent.mkdir(parents=True, exist_ok=True)


def buildable(target, name):
    return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="{name}" BlueprintName="{name.split(".")[0]}" ReferencedContainer="container:PotPatrol.xcodeproj"/>'


scheme.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2600" version="1.3">
 <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries>
  <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{buildable(app, "PotPatrol.app")}</BuildActionEntry>
 </BuildActionEntries></BuildAction>
 <TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES">
  <Testables><TestableReference skipped="NO">{buildable(tests, "PotPatrolUITests.xctest")}</TestableReference></Testables>
 </TestAction>
 <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{buildable(app, "PotPatrol.app")}</BuildableProductRunnable></LaunchAction>
 <ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{buildable(app, "PotPatrol.app")}</BuildableProductRunnable></ProfileAction>
 <AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>''', encoding="utf-8")
base_info = dict(CFBundleDevelopmentRegion="$(DEVELOPMENT_LANGUAGE)", CFBundleExecutable="$(EXECUTABLE_NAME)",
                 CFBundleIdentifier="$(PRODUCT_BUNDLE_IDENTIFIER)", CFBundleInfoDictionaryVersion="6.0",
                 CFBundleName="$(PRODUCT_NAME)", CFBundleDisplayName="Pot Patrol", CFBundlePackageType="APPL",
                 CFBundleShortVersionString="1.0", CFBundleVersion="1", LSRequiresIPhoneOS=True,
                 NSCameraUsageDescription="Pot Patrol records road video for you to review and report hazards.",
                 NSLocationWhenInUseUsageDescription="Pot Patrol saves approximate locations with your drive video. Recording also works without location.",
                 NSLocalNetworkUsageDescription="Connect to your team's local analysis server during development.",
                 UILaunchScreen={}, UISupportedInterfaceOrientations=["UIInterfaceOrientationPortrait"],
                 UIApplicationSceneManifest=dict(UIApplicationSupportsMultipleScenes=False))
for mode in ("Debug", "Release"):
    info = base_info.copy()
    if mode == "Debug":
        info["NSAppTransportSecurity"] = dict(NSAllowsArbitraryLoads=True)
    (ROOT / f"NativeApp/Info-{mode}.plist").write_bytes(plistlib.dumps(info))
print("Generated PotPatrol.xcodeproj, shared scheme, and app property lists.")
