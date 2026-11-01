// SPDX-License-Identifier: Apache-2.0
// Host-only OCR reference on synthetic QEMU captures. This is not an XOS port.
import Foundation
import Vision

guard CommandLine.arguments.count > 1 else { exit(2) }
var runs: [[String: Any]] = []
for path in CommandLine.arguments.dropFirst() {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
    let start = DispatchTime.now().uptimeNanoseconds
    do {
        try handler.perform([request])
        let elapsed = DispatchTime.now().uptimeNanoseconds - start
        let lines: [[String: Any]] = (request.results ?? []).compactMap { item in
            guard let text = item.topCandidates(1).first else { return nil }
            return ["text": text.string, "confidence": text.confidence,
                    "normalizedBounds": [item.boundingBox.minX, item.boundingBox.minY,
                                         item.boundingBox.width, item.boundingBox.height]]
        }
        runs.append(["path": path, "status": "OK", "hostElapsedNs": String(elapsed), "lines": lines])
    } catch {
        runs.append(["path": path, "status": "FAILED", "error": String(describing: error)])
    }
}
let result: [String: Any] = ["scope": "HOST_ONLY_VISION_OCR_REFERENCE", "runs": runs,
                            "xosOCRPort": "NOT_IMPLEMENTED", "actionExecution": "NOT_RUN"]
let data = try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data([10]))
