import Foundation
import Glibc
import CR2T

typealias Doc = [String: Any]
enum R2TError: Error, CustomStringConvertible {
    case config, io, database(Int), network, timeout, reddit, telegram
    case rejected, forbidden, rateLimit, lease, announcement, media, template, unknownTask, incompletePort
    var description: String {
        switch self {
        case .database(let code): return "Database(\(code))"
        case .config: return "Config"
        case .io: return "Io"
        case .network: return "Network"
        case .timeout: return "Timeout"
        case .reddit: return "Reddit"
        case .telegram: return "Telegram"
        case .rejected: return "Rejected"
        case .forbidden: return "Forbidden"
        case .rateLimit: return "RateLimit"
        case .lease: return "Lease"
        case .announcement: return "Announcement"
        case .media: return "Media"
        case .template: return "Template"
        case .unknownTask: return "UnknownTask"
        case .incompletePort: return "IncompletePort"
        }
    }
}
let null = NSNull()
func now() -> Double { Date().timeIntervalSince1970 }
func object(_ value: Any?) -> Doc { value as? Doc ?? [:] }
func array(_ value: Any?) -> [Any] { value as? [Any] ?? [] }
func text(_ value: Any?) -> String { value as? String ?? "" }
func number(_ value: Any?, _ fallback: Double = 0) -> Double {
    if let n = value as? NSNumber { return n.doubleValue }
    if let d = value as? Doc {
        for key in ["$numberLong", "$numberInt", "$numberDouble"] {
            if let n = Double(text(d[key])) { return n }
        }
    }
    return fallback
}
func truth(_ value: Any?) -> Bool {
    guard let value, !(value is NSNull) else { return false }
    if let s = value as? String { return !s.isEmpty }
    if let n = value as? NSNumber { return n.doubleValue != 0 }
    if let a = value as? [Any] { return !a.isEmpty }
    if let d = value as? Doc { return !d.isEmpty }
    return true
}
func jsonData(_ value: Any) throws -> Data {
    do { return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .fragmentsAllowed]) }
    catch { throw R2TError.config }
}
func json(_ value: Any) throws -> String { String(decoding: try jsonData(value), as: UTF8.self) }
func parseJSON(_ data: Data) throws -> Any {
    do { return try JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]) }
    catch { throw R2TError.config }
}
func dateBSON(_ date: Date = Date()) -> Doc {
    ["$date": ["$numberLong": String(Int64(date.timeIntervalSince1970 * 1000))]]
}
func bsonDate(_ value: Any?) -> Date? {
    guard let v = object(value)["$date"] else { return nil }
    if let s = v as? String { return isoDate(s) }
    return Date(timeIntervalSince1970: number(v) / 1000)
}
func isoDate(_ string: String) -> Date? {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.date(from: string) ?? ISO8601DateFormatter().date(from: string)
}
func idString(_ value: Any?) -> String {
    if let s = value as? String { return s }
    if let oid = object(value)["$oid"] as? String { return oid }
    return (try? json(value ?? null)) ?? ""
}
func integer64(_ value: Any?) -> Int64 {
    if let n = value as? NSNumber { return n.int64Value }
    if let s = object(value)["$numberLong"] as? String { return Int64(s) ?? 0 }
    return 0
}
func safeError(_ error: Error) -> R2TError { error as? R2TError ?? .io }
private let logLock = NSLock()
private let logFormatter: DateFormatter = {
    let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"; return f
}()
func log(_ message: String, warning: Bool = false) {
    logLock.lock(); defer { logLock.unlock() }
    let line = "\(logFormatter.string(from: Date())) - r2t.swift - \(warning ? "WARNING" : "INFO") - \(message)\n"
    FileHandle.standardError.write(Data(line.utf8))
}
func pause(_ low: Double, _ high: Double) { Thread.sleep(forTimeInterval: Double.random(in: low..<high)) }
func shortSleep(_ coefficient: Double = 1) { pause(2 * coefficient, 4 * coefficient) }
func longSleep(_ coefficient: Double = 1) { pause(8 * coefficient, 20 * coefficient) }
func digest(_ value: String, algorithm: String = "SHA256") throws -> String {
    let data = Data(value.utf8)
    let result = data.withUnsafeBytes { bytes in r2t_digest(algorithm, bytes.baseAddress, bytes.count) }
    guard let result else { throw R2TError.io }
    defer { r2t_free(result) }
    return String(cString: result)
}
func format(_ template: String, _ fields: [String: String]) throws -> String {
    let chars = Array(template); var i = 0; var result = ""
    while i < chars.count {
        let c = chars[i]; i += 1
        if c == "{" || c == "}" {
            if i < chars.count && chars[i] == c { result.append(c); i += 1; continue }
            if c == "}" { throw R2TError.template }
            let start = i
            while i < chars.count && chars[i] != "}" { i += 1 }
            guard i < chars.count, let value = fields[String(chars[start..<i])] else { throw R2TError.template }
            result += value; i += 1
        } else { result.append(c) }
    }
    return result
}
func human(_ value: Int) -> String {
    if abs(value) < 1000 { return String(value) }
    var v = Double(value); var index = 0
    while abs(v) >= 1000 && index < 5 { index += 1; v = (v / 100).rounded(.toNearestOrEven) / 10 }
    return String(format: "%.1f%@", v, ["", "k", "M", "G", "T", "P"][index])
}
enum Supply { case sent, reject, skip, stop }

struct Config {
    var values: Doc
    let path: URL
    let app: URL
    let root: URL
    init(path: String) throws {
        self.path = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
        app = self.path.deletingLastPathComponent().deletingLastPathComponent()
        root = app.deletingLastPathComponent()
        guard let raw = r2t_yaml_json(self.path.path) else { throw R2TError.config }
        defer { r2t_free(raw) }
        values = object(object(try parseJSON(Data(String(cString: raw).utf8)))["value"])
    }
    var workers: Int { Int(number(object(values["pool"])["size"], Double(ProcessInfo.processInfo.activeProcessorCount))) }
    var maxPending: Int { Int(number(object(values["consumer"])["max_pending"], Double(workers))) }
    var batchSize: Int { Int(number(object(values["consumer"])["batch_size"], Double(workers * 2))) }
    var cronPath: URL {
        let value = text(values["cron_file"])
        return value.hasPrefix("/") ? URL(fileURLWithPath: value) : app.appendingPathComponent(value)
    }
    func database() throws -> Database {
        let db = object(values["db"]); let host = text(db["host"])
        return try Database(uri: host.contains("://") ? host : "mongodb://\(host)", name: text(db["name"]))
    }
}
