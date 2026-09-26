# Pot Patrol real clips and phone demo

Physical phone, deployed server and real analyzer acceptance remain outstanding. No real clips have been provided; bundled media is synthetic.

## Two real clips

Record one 10–30 second real pothole clip and one clean stretch as a passenger or while parked. Set up before motion. Keep originals; share privately with Developers 2 and 3. Clean media tests the real analyzer's zero-hazard result.

In Pot Patrol, Start, wait for recording/GPS, then Stop while parked. MP4, GPS, duration and UTC persist. Outside-app clips have no correlated GPS or reliably known first-frame UTC; leave those unknown.

Before the Mac is available, iPhone Camera clips can be analyzer inputs. If MOV/HEVC needs conversion, an available FFmpeg on Windows can produce H.264 MP4:

```powershell
ffmpeg -i original.mov -map 0:v:0 -an -c:v libx264 -pix_fmt yuv420p -movflags +faststart output.mp4
```

Keep originals; conversion creates no correlated GPS/UTC. Do not commit real media publicly. Developer 3 should confirm expected pothole offsets and clean-clip ground truth.

## First Mac step

Open `ios/PotPatrol.xcodeproj`, select **PotPatrol** and an iPhone Simulator, then Run. Verify **Sample drive → Stop and save → Results → Pothole → Review report**. Then select the connected phone and your Apple team in Signing & Capabilities. Xcode must support its actual iOS.

## Live acceptance

1. Enter Developer 2's HTTPS URL/token. Confirm Developer 3's real analyzer is active.
2. Grant permissions while parked; capture a short passenger/parked drive. Review playable video and GPS count.
3. Upload, inspect real processing states, reopen and confirm the same saved drive resumes.
4. Review server pothole/private evidence/offset/optional confidence and severity/approximate location/editable report/destination. Compare timing with original media; confirm UTC survives reopening.
5. Test a clean clip for zero hazards and a GPS-denied clip for a visible hazard without a map.
6. Test network retry, failed processing, unsupported destination and retained media. Explicit force-quit cancels background transfers; reopen/retry.
7. Only verified destinations open portals. Attach shared media manually where needed. Confirmation requires an actual receipt.

## Fallback / evidence

Sample scenarios are labeled **Demo fixture · not real analysis**. They are deterministic backups, not real-detection acceptance.

| Check | Result |
| --- | --- |
| Package / iPhone SDK compilation | Passed macOS CI 36271791265 |
| HTTP MP4 / GPS retries / private evidence / report / no GPS | Passed CI 36271791265 with synthetic worker |
| Native Release / simulator UI | CI verification in progress |
| Mac / Xcode / installed iOS | Pending; iPhone 17 Pro or Pro Max planned |
| Real pothole / clean clip | Pending capture |
| Physical UTC/GPS timing / live real analyzer | Pending Mac/phone/server |
