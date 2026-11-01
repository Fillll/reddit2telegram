import Foundation
import CoreFoundation

func oldestDate() -> Doc { ["$date": ["$numberLong": "-62135596800000"]] }
func identifiers(_ event: Doc, _ key: String) throws -> [Int64] {
    guard let values = event[key] as? [Any] else { throw R2TError.config }
    return try values.map { value in
        guard let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(),
              n.doubleValue.isFinite, n.doubleValue.rounded(.towardZero) == n.doubleValue else { throw R2TError.config }
        return n.int64Value
    }
}
func duplicateKey(_ error: Error) -> Bool {
    if case R2TError.database(11000) = error { return true }; return false
}
final class Lease {
    let db: Database
    let key: String
    let owner = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
    var previousOwner: String?
    init(db: Database, key: String) { self.db = db; self.key = key }
    func acquire() throws -> Bool {
        do {
            try db.update("settings", ["_id": key], ["$setOnInsert": ["setting": key, "expires_at": oldestDate()]], upsert: true)
        } catch { if !duplicateKey(error) { throw error } }
        let current = Date()
        let response = try db.command("findAndModify", "settings", ["query": ["_id": key, "expires_at": ["$lte": dateBSON(current)]],
            "update": ["$set": ["owner": owner, "expires_at": dateBSON(current.addingTimeInterval(7200))]], "new": false])
        let previous = response["value"] as? Doc
        previousOwner = previous?["owner"] as? String
        return previous != nil
    }
    func renew() throws {
        let current = Date()
        let response = try db.command("update", "settings", ["updates": [[
            "q": ["_id": key, "owner": owner, "expires_at": ["$gt": dateBSON(current)]],
            "u": ["$set": ["expires_at": dateBSON(current.addingTimeInterval(7200))]], "multi": false, "upsert": false]]])
        guard number(response["n"]) != 0 else { throw R2TError.lease }
    }
    func release() throws { try db.update("settings", ["_id": key, "owner": owner], ["$set": ["expires_at": oldestDate()]]) }
}
enum AckMode { case achievement, anniversary(String) }
final class Checkpoint: AckSink {
    let db: Database
    let selector: Doc
    let mode: AckMode
    private let lock = NSLock()
    private var recorded: [Int64]
    init(db: Database, selector: Doc, mode: AckMode, ids: [Int64]) {
        self.db = db; self.selector = selector; self.mode = mode; recorded = ids
    }
    var ids: [Int64] { lock.lock(); defer { lock.unlock() }; return recorded }
    func record(_ ids: [Int64]) throws {
        lock.lock(); recorded += ids; let all = recorded; lock.unlock()
        let update: Doc
        switch mode {
        case .achievement: update = ["$addToSet": ["message_ids": ["$each": ids]]]
        case .anniversary(let path): update = ["$set": [path + ".state": "sent", path + ".message_ids": all, path + ".sent_at": dateBSON()]]
        }
        let response = try db.command("update", "settings", ["updates": [["q": selector, "u": update, "multi": false, "upsert": false]]])
        if case .anniversary = mode, number(response["n"]) == 0 { throw R2TError.lease }
    }
}
