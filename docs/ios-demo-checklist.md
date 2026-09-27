# Pot Patrol real clips and phone demo

Physical phone, deployed server and real analyzer acceptance remain outstanding. No real clips have been provided; bundled media is synthetic.

## Two real clips

Record one 30–60 second real pothole clip and one clean stretch as a passenger or while parked, matching Developer 3's requested 30–90 second range. Set up before motion. Keep originals; share privately with Developers 2 and 3. Clean media tests the real analyzer's zero-hazard result.

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
7. Review candidate names, URLs, official sources and reason; choose the road owner yourself before opening its page. A candidate choice stays `needs_review`; handoff says Portal opened. Attach shared evidence manually. Full video is off by default. Confirmation requires an actual receipt.
8. Refresh a cached draft after Developer 2's flattening fix. Check the latest category/description/location, coordinate edit and restoration, and receipt history.

## Fallback / evidence

Sample scenarios and server results with `analysis_mode:"fixture"` are labeled **Demo fixture · not real analysis**, including copied/shared report text. They are deterministic backups, not real-detection acceptance. A missing analysis mode is not proof of real inference.

| Check | Result |
| --- | --- |
| Package / iPhone SDK compilation | Passed [macOS CI 36293356119](https://github.com/smandava0512/PotPatrol/actions/runs/36293356119); 33 unit checks passed (live integration skipped in the ordinary unit run) |
| HTTP MP4 / GPS retries / private evidence / report / no GPS | Passed CI 36293356119 in the separate live HTTP test with synthetic worker |
| Native Release / simulator UI | Passed CI 36293356119; all 6 UI scenarios passed |
| Mac / Xcode / installed iOS | Pending; iPhone 17 Pro or Pro Max planned |
| Real pothole / clean clip | Pending capture |
| Physical UTC/GPS timing / live real analyzer | Pending Mac/phone/server |
| Report refresh / candidates / coordinate restoration / opt-in video | Passed CI 36293356119, including refresh after relaunch, candidate handoff without confirmation, and video off by default |

On 2026-09-27, public `https://api.potpatrol.miami/health` returned `status:ok`. Authenticated real-model acceptance still needs a valid UUID `drive_id` and private device credentials; physical app rendering remains unconfirmed.
