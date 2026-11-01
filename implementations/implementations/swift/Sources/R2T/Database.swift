import Foundation
import CR2T

final class Database {
    private let pool: UnsafeMutableRawPointer
    let name: String
    init(uri: String, name: String) throws {
        guard let pool = r2t_db_open(uri), !name.isEmpty else { throw R2TError.database(-1) }
        self.pool = pool; self.name = name
    }
    deinit { r2t_db_close(pool) }
    func command(_ command: String, _ value: Any, _ fields: Doc = [:]) throws -> Doc {
        // MongoDB uses the first BSON key as the command name. Keep it first,
        // independent of Swift Dictionary/JSONSerialization key ordering.
        let rest = try json(fields)
        let wire = "{" + (try json(command)) + ":" + (try json(value)) + (fields.isEmpty ? "}" : "," + rest.dropFirst())
        var code: Int32 = 0
        let raw = r2t_db_command(pool, name, wire, &code)
        defer { if let raw { r2t_free(raw) } }
        guard let raw else { throw R2TError.database(Int(code)) }
        let result = object(try parseJSON(Data(String(cString: raw).utf8)))
        if code != 0 { throw R2TError.database(Int(code)) }
        if let error = array(result["writeErrors"]).first { throw R2TError.database(Int(number(object(error)["code"], -1))) }
        if let error = result["writeConcernError"] { throw R2TError.database(Int(number(object(error)["code"], -1))) }
        return result
    }
    func find(_ collection: String, _ filter: Doc = [:], sort: Doc = [:], limit: Int = 0, projection: Doc = [:]) throws -> [Doc] {
        var fields: Doc = ["filter": filter, "batchSize": 1000]
        if !sort.isEmpty { fields["sort"] = sort }
        if limit > 0 { fields["limit"] = limit }
        if !projection.isEmpty { fields["projection"] = projection }
        var response = try command("find", collection, fields)
        var cursor = object(response["cursor"])
        var documents = array(cursor["firstBatch"]).map(object)
        var cursorID = integer64(cursor["id"])
        while cursorID != 0 {
            response = try command("getMore", ["$numberLong": String(cursorID)], ["collection": collection, "batchSize": 1000])
            cursor = object(response["cursor"]); documents += array(cursor["nextBatch"]).map(object)
            cursorID = integer64(cursor["id"])
        }
        return documents
    }
    func one(_ collection: String, _ filter: Doc = [:], sort: Doc = [:]) throws -> Doc? {
        try find(collection, filter, sort: sort, limit: 1).first
    }
    @discardableResult func update(_ collection: String, _ filter: Doc, _ update: Doc, multi: Bool = false, upsert: Bool = false) throws -> Int {
        let response = try command("update", collection, ["updates": [["q": filter, "u": update, "multi": multi, "upsert": upsert]], "ordered": true])
        return Int(number(response["nModified"]))
    }
    func claim(_ collection: String, _ filter: Doc, _ update: Doc, sort: Doc = [:], projection: Doc = [:], upsert: Bool = false) throws -> Doc? {
        var fields: Doc = ["query": filter, "update": update, "new": true, "upsert": upsert]
        if !sort.isEmpty { fields["sort"] = sort }
        if !projection.isEmpty { fields["fields"] = projection }
        let response = try command("findAndModify", collection, fields)
        return response["value"] as? Doc
    }
    @discardableResult func insert(_ collection: String, _ documents: [Doc]) throws -> Int {
        if documents.isEmpty { return 0 }
        return Int(number(try command("insert", collection, ["documents": documents, "ordered": true])["n"]))
    }
    @discardableResult func delete(_ collection: String, _ filter: Doc, one: Bool = false) throws -> Int {
        Int(number(try command("delete", collection, ["deletes": [["q": filter, "limit": one ? 1 : 0]], "ordered": true])["n"]))
    }
    func count(_ collection: String, _ filter: Doc = [:]) throws -> Int {
        Int(number(try command("count", collection, ["query": filter])["n"]))
    }
}
