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
            reveal(app.buttons["demoScenarios"])
            app.buttons["demoScenarios"].tap()
            reveal(app.buttons[scenario])
            app.buttons[scenario].tap()
        } else { reveal(app.buttons["demoDrive"]); app.buttons["demoDrive"].tap() }
        guard app.buttons["stopRecording"].waitForExistence(timeout: 15) else {
            XCTFail("Recording did not show its Stop control.\n" + app.debugDescription)
            return
        }
        app.buttons["stopRecording"].tap()
    }
    func testSavedDriveDeletionRequiresConfirmationAndDisappearsAfterSuccess() {
        finishDemo("demoNoHazards")
        XCTAssertTrue(app.staticTexts["0 hazards"].waitForExistence(timeout: 20))
        let back = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 20))
        back.tap()
        let drive = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'drive_' ")).firstMatch
        reveal(drive)
        XCTAssertTrue(drive.waitForExistence(timeout: 10), app.debugDescription)
        let delete = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'deleteDrive_' ")).firstMatch
        reveal(delete)
        delete.tap()
        let warning = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@ AND label CONTAINS %@",
                                                           "Deletes this drive’s video, GPS", "connected server")).firstMatch
        XCTAssertTrue(warning.exists)
        app.buttons["Cancel"].tap()
        XCTAssertTrue(drive.exists)
        delete.tap()
        app.buttons["Delete from iPhone and server"].tap()
        let gone = NSPredicate { _, _ in !drive.exists }
        expectation(for: gone, evaluatedWith: nil)
        waitForExpectations(timeout: 10)
    }
    private func reveal(_ element: XCUIElement) {
        for _ in 0..<5 where !element.isHittable { app.swipeUp() }
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
        let originalDescription = description.value as? String
        description.tap()
        description.typeText(" Passenger reviewed this evidence.")
        if app.buttons["dismissReportKeyboard"].exists { app.buttons["dismissReportKeyboard"].tap() }
        reveal(app.buttons["saveDraft"])
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
        reveal(app.buttons["refreshDraft"])
        app.buttons["refreshDraft"].tap()
        app.buttons["Replace local draft"].tap()
        let refreshed = NSPredicate { _, _ in
            self.app.textViews["reportDescription"].value as? String == originalDescription
        }
        expectation(for: refreshed, evaluatedWith: nil)
        waitForExpectations(timeout: 10)
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
        let share = app.buttons["shareReport"]
        reveal(share)
        XCTAssertTrue(share.waitForExistence(timeout: 5))
        XCTAssertTrue(share.isEnabled)
        let video = app.switches["includeFullVideo"]
        XCTAssertTrue(video.exists)
        XCTAssertEqual(video.value as? String, "0")
        XCTAssertEqual(share.label, "Share text and evidence")
    }
    func testCandidateSelectionEnablesHandoffWithoutConfirmingSubmission() {
        finishDemo("demoCandidates")
        reviewReport()
        let candidate = app.buttons["candidate_miami-dade-dtpw-311"]
        reveal(candidate)
        XCTAssertTrue(candidate.waitForExistence(timeout: 5))
        candidate.tap()
        XCTAssertEqual(candidate.label, "Selected by you")
        let portal = app.buttons["openPortal"]
        for _ in 0..<9 where !portal.isHittable { app.swipeUp() }
        XCTAssertTrue(portal.exists)
        XCTAssertTrue(portal.isEnabled)
        XCTAssertEqual(portal.label, "Open selected agency page")
        let handoff = app.staticTexts["handoffState"]
        for _ in 0..<5 where !handoff.isHittable { app.swipeUp() }
        XCTAssertEqual(handoff.label, "Draft prepared")
    }
}
