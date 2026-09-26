import XCTest

final class PotPatrolUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchEnvironment["POTPATROL_UI_TEST_ID"] = UUID().uuidString
        app.launch()
    }
    private func finishDemo(_ scenario: String? = nil) {
        if let scenario {
            app.buttons["demoScenarios"].tap()
            app.buttons[scenario].tap()
        } else { app.buttons["demoDrive"].tap() }
        XCTAssertTrue(app.buttons["stopRecording"].waitForExistence(timeout: 10))
        app.buttons["stopRecording"].tap()
    }
    private var hazard: XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'hazard_'")).firstMatch
    }
    private func reviewReport() {
        XCTAssertTrue(hazard.waitForExistence(timeout: 20))
        hazard.tap()
        let review = app.buttons["reviewReport"]
        for _ in 0..<4 where !review.isHittable { app.swipeUp() }
        XCTAssertTrue(review.waitForExistence(timeout: 5))
        review.tap()
        XCTAssertTrue(app.textViews["reportDescription"].waitForExistence(timeout: 10))
    }
    func testDraftEditsAndDriveSurviveRelaunch() {
        finishDemo()
        reviewReport()
        let description = app.textViews["reportDescription"]
        description.tap()
        description.typeText(" Passenger reviewed this evidence.")
        app.swipeUp()
        app.buttons["saveDraft"].tap()
        XCTAssertTrue(app.staticTexts["Edits saved on this iPhone"].waitForExistence(timeout: 5))
        app.terminate()
        app.launch()
        let savedDrive = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'drive_'")).firstMatch
        for _ in 0..<3 where !savedDrive.isHittable { app.swipeUp() }
        XCTAssertTrue(savedDrive.waitForExistence(timeout: 10))
        savedDrive.tap()
        reviewReport()
        XCTAssertTrue((app.textViews["reportDescription"].value as? String)?.contains("Passenger reviewed") == true)
    }
    func testMissingGPSKeepsHazardVisible() {
        finishDemo("demoNoGPS")
        XCTAssertTrue(hazard.waitForExistence(timeout: 20))
        hazard.tap()
        let missing = app.staticTexts["locationUnavailable"]
        for _ in 0..<4 where !missing.isHittable { app.swipeUp() }
        XCTAssertTrue(missing.exists)
    }
    func testNoHazards() {
        finishDemo("demoNoHazards")
        XCTAssertTrue(app.staticTexts["0 hazards"].waitForExistence(timeout: 20))
        XCTAssertFalse(hazard.exists)
    }
    func testProcessingFailure() {
        finishDemo("demoFailure")
        XCTAssertTrue(app.buttons["Retry"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["Your local files are retained."].exists)
    }
    func testUnsupportedDestinationDisablesPortalAndKeepsDraft() {
        finishDemo("demoUnsupported")
        reviewReport()
        let portal = app.buttons["openPortal"]
        for _ in 0..<5 where !portal.isHittable { app.swipeUp() }
        XCTAssertTrue(portal.exists)
        XCTAssertFalse(portal.isEnabled)
        XCTAssertTrue(app.staticTexts["destinationStatus"].label.contains("not supported"))
        XCTAssertTrue(app.buttons["Share text, evidence, and saved video"].exists)
    }
}
