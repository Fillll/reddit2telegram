import Foundation
import CR2T

struct HTTPResponse {
    let status: Int
    let body: Data
    let headers: [String: String]
    let tooLarge: Bool
    func json() throws -> Any {
        do { return try parseJSON(body) } catch { throw R2TError.network }
    }
}
final class HTTP {
    private let handle: UnsafeMutableRawPointer
    let metrics: Metrics
    private let telegram: Bool
    init(metrics: Metrics, telegram: Bool = false) throws {
        guard let handle = r2t_http_open() else { throw R2TError.network }
        self.handle = handle; self.metrics = metrics; self.telegram = telegram
    }
    deinit { r2t_http_close(handle) }
    func request(_ method: String, _ url: String, headers: [String: String] = [:],
                 body: Data = Data(), multipart: Doc? = nil,
                 output: URL? = nil, limit: UInt64 = 0) throws -> HTTPResponse {
        let prefix = telegram ? "telegram" : "http"
        let head = method == "HEAD"
        let connect = telegram ? 30 : (head ? 3 : 5)
        let read = telegram ? 30 : (head ? 8 : 20)
        let headerLines = headers.map { "\($0.key): \($0.value)" }.joined(separator: "\n")
        let specification = try multipart.map(json)
        metrics.count(prefix + "_request_attempts")
        let raw = body.withUnsafeBytes { bytes in
            r2t_http_request(handle, method, url, headerLines, bytes.baseAddress, bytes.count,
                specification, output?.path, limit, connect, read, telegram ? 0 : 1)
        }
        guard let raw else { metrics.count(prefix + "_transport_errors"); throw R2TError.network }
        defer { r2t_response_free(raw) }
        let response = raw.pointee
        metrics.count(prefix + "_requests", response.requests)
        if response.requests > 1 { metrics.count(prefix + "_request_attempts", response.requests - 1) }
        metrics.count(prefix + "_http_errors", response.http_errors)
        metrics.count(prefix + "_rate_limits", response.rate_limits)
        metrics.count(prefix + "_response_body_bytes", response.received)
        if telegram { metrics.count("telegram_request_body_bytes", response.sent) }
        if response.error != 0 && response.too_large == 0 {
            metrics.count(prefix + "_transport_errors")
            // CURLE_OPERATION_TIMEDOUT=28, or our idle-progress callback=42.
            throw response.error == 28 || response.error == 42 ? R2TError.timeout : R2TError.network
        }
        var fields: [String: String] = [:]
        if let rawHeaders = response.headers {
            for line in String(cString: rawHeaders).components(separatedBy: "\r\n") {
                guard let separator = line.firstIndex(of: ":") else { continue }
                fields[String(line[..<separator]).lowercased()] = line[line.index(after: separator)...].trimmingCharacters(in: .whitespaces)
            }
        }
        let data = response.body.map { Data(bytes: $0, count: response.length) } ?? Data()
        return HTTPResponse(status: Int(response.status), body: data, headers: fields, tooLarge: response.too_large != 0)
    }
    func download(_ url: String, to path: URL, limit: UInt64) -> Bool {
        let ok: Bool
        do {
            let response = try request("GET", url, output: path, limit: limit)
            ok = (200..<300).contains(response.status) && !response.tooLarge
        } catch { ok = false }
        if !ok { try? FileManager.default.removeItem(at: path) }
        return ok
    }
    func metadata(_ url: String) throws -> String {
        let response = try request("GET", url, limit: 1024 * 1024)
        guard (200..<300).contains(response.status), !response.tooLarge else { throw R2TError.media }
        return String(decoding: response.body, as: UTF8.self)
    }
    func api(token: String, method: String, params: Doc, video: URL? = nil) throws -> Any {
        let response: HTTPResponse
        if let video {
            var fields: [String: String] = [:]
            for (key, value) in params { fields[key] = value as? String ?? (try json(value)) }
            response = try request("POST", "https://api.telegram.org/bot\(token)/\(method)",
                multipart: ["fields": fields, "files": ["video": ["path": video.path, "filename": "video.mp4", "content_type": "video/mp4"]]])
        } else {
            response = try request("POST", "https://api.telegram.org/bot\(token)/\(method)",
                headers: ["Content-Type": "application/json"], body: try jsonData(params))
        }
        let body = object(try response.json())
        guard (200..<300).contains(response.status), truth(body["ok"]) else {
            switch response.status {
            case 400: throw R2TError.rejected
            case 403: throw R2TError.forbidden
            case 429: throw R2TError.rateLimit
            default: throw R2TError.telegram
            }
        }
        let result = body["result"] ?? null
        if method.hasPrefix("send") || method == "forwardMessage" { metrics.delivery(result) }
        return result
    }
}
func percentEncode(_ value: String) -> String {
    value.addingPercentEncoding(withAllowedCharacters: CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")) ?? ""
}
func formBody(_ fields: [String: String]) -> Data {
    Data(fields.map { percentEncode($0.key) + "=" + percentEncode($0.value) }.joined(separator: "&").utf8)
}
