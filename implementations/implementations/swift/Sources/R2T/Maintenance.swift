import Foundation
import Glibc

enum Maintenance {
    static func cleaner(_ app: App, sender: Sender) throws -> Supply {
        let memory = try String(contentsOfFile: "/proc/meminfo", encoding: .utf8)
        guard let line = memory.components(separatedBy: "\n").first(where: { $0.hasPrefix("MemFree:") }),
              let kb = Double(line.split(whereSeparator: { $0.isWhitespace }).dropFirst().first ?? "") else { throw R2TError.io }
        let free = kb / 1024
        let deleted = try clean(config: app.config)
        var disk = statvfs(); guard statvfs("/", &disk) == 0 else { throw R2TError.io }
        let available = Double(disk.f_bavail) * Double(disk.f_frsize) / pow(1024, 3)
        let output = try commandOutput("vnstat", ["-m"])
        let lines = output.components(separatedBy: "\n")
        guard lines.count >= 4 else { throw R2TError.io }
        let trafficParts = lines[lines.count - 4].components(separatedBy: " | ")
        let estimateParts = lines[lines.count - 2].components(separatedBy: "|")
        guard trafficParts.count >= 2 && estimateParts.count >= 2 else { throw R2TError.io }
        let traffic = trafficParts[trafficParts.count - 2].trimmingCharacters(in: .whitespacesAndNewlines)
        let estimate = estimateParts[estimateParts.count - 2].trimmingCharacters(in: .whitespacesAndNewlines)
        let aggregate = try app.db.command("aggregate", "tasks", ["pipeline": [["$group": ["_id": "$status", "count": ["$sum": 1]]]], "cursor": [:]])
        var counts: [Int: Int] = [:]
        for record in array(object(aggregate["cursor"])["firstBatch"]).map(object) { counts[Int(number(record["_id"]))] = Int(number(record["count"])) }
        let previous = try app.db.one("settings", ["setting": "tasks-stati"])
        var data = object(previous?["data"])
        let cycles = Int(data.values.map { number(object($0)["cycles_cnt"]) }.max() ?? 0) + 1
        var body = String(format: "Free memory: %.3fMB.\nDeleted files: %.3fGB.\nAvailable disk space: %.3fGB.\nCurrent month traffic: %@.\nCurrent month estimate: %@.\nTasks' stati:\n", free, Double(deleted) / pow(1024, 3), available, traffic, estimate)
        var removed = 0
        for (status, name) in [(1,"NEW"),(2,"IN_PROGRESS"),(3,"SUCCESS"),(4,"FAILED"),(5,"SCHEDULED")] {
            let old = object(data[name]); let count = counts[status] ?? 0; let total = Int(number(old["amt"])) + count
            data[name] = ["amt": total, "cycles_cnt": Int(number(old["cycles_cnt"])) + 1]
            body += String(format: "  →  %@: %d (avg: %.3f)\n", name, count, Double(total) / Double(cycles))
            removed += try app.db.delete("tasks", ["status": status])
        }
        body += "Deleted tasks: \(removed).\nTotal cycles: \(cycles).\n"
        try app.db.update("settings", ["setting": "tasks-stati"], ["$set": ["data": data]], upsert: true)
        try sender.sendText(body)
        return .stop
    }
    static func publicChannels(_ app: App, sender: Sender) throws -> [String] {
        var unique: [String: Date] = [:]
        for module in try Channels.publicModules(app) {
            guard let channel = try Channels.identity(app, module: module).0 as? String else { throw R2TError.config }
            if !channel.contains("@") || ["@r_channels_test", "@r_channels"].contains(channel) { continue }
            guard let first = try sender.db.one("urls", ["channel": channel.lowercased()], sort: ["ts": 1]),
                  let date = bsonDate(first["ts"]) else { throw R2TError.config }
            unique[channel] = date
        }
        return unique.keys.sorted { unique[$0]! < unique[$1]! }
    }
    static func firstMembers(_ app: App, filter: Doc, sort: Doc) throws -> Double {
        for record in try app.db.find("stats", filter, sort: sort, limit: 100) {
            if record["members_cnt"] is NSNumber { return number(record["members_cnt"]) }
        }
        throw R2TError.config
    }
    static func weekly(_ app: App, sender: Sender) throws -> Supply {
        let channels = try publicChannels(app, sender: sender)
        var new: [String] = []; var growers: [(Double, String)] = []
        let cutoff = dateBSON(Date(timeIntervalSinceNow: -7 * 86400))
        for channel in channels {
            let filter: Doc = ["channel": channel.lowercased()]
            guard let first = try app.db.one("stats", filter, sort: ["ts": 1]),
                  let latest = try app.db.one("stats", filter, sort: ["ts": -1]),
                  let start = bsonDate(first["ts"]), let end = bsonDate(latest["ts"]) else { throw R2TError.config }
            if Int(end.timeIntervalSince(start) / 86400) <= 31 { new.append(channel) }
            let previous = try firstMembers(app, filter: ["channel": channel.lowercased(), "ts": ["$gte": cutoff]], sort: ["ts": 1])
            let current = try firstMembers(app, filter: filter, sort: ["ts": -1])
            if current - previous >= 10 { growers.append((current - previous, channel)) }
        }
        growers.sort { $0.0 > $1.0 }
        guard let featured = channels.randomElement() else { throw R2TError.config }
        var body = "<b>Weekend news</b>\n\n"
        if !new.isEmpty { body += "🎉 Welcome to newly active channels: \(new.joined(separator: ", ")). 🎈🎈\n\n" }
        body += "🏆 Channel of the week: \(featured). Join and enjoy!\n\n"
        if !growers.isEmpty { body += "🔥 Hottest channels of the week: \(growers.prefix(3).map { $0.1 }.joined(separator: ", ")).\n\n" }
        body += "🙋\nQ: How can I help?\nA: Support us on Patreon and promote your favorite channels!\n\nQ: How to make similar channels?\nA: Ask at @r_channels or use manual at https://github.com/Fillll/reddit2telegram.\n\nQ: Where to donate?\nA: Patreon: https://www.patreon.com/reddit2telegram."
        try sender.sendText(body, parse: "HTML"); Thread.sleep(forTimeInterval: 2)
        for (index, page) in chunks(channels, 100).enumerated() {
            var body = index == 0 ? "⬇️ All active channels:\n" : ""
            body += page.enumerated().map { String(format: "%02d. %@", index * 100 + $0.offset + 1, $0.element) }.joined(separator: "\n")
            try sender.sendText(body); Thread.sleep(forTimeInterval: 2)
        }
        return .stop
    }
    static let help = "Send channel data in one message:\nsubreddit: https://reddit.com/r/example\nchannel: @example_channel\ntags: #tag1 #tag2 #tag3\n\nOr send it step by step:\n1. subreddit\n2. channel\n3. tags\n\nCommands:\n/newchannel to restart\n/cancel to clear the current draft"
    static func normalize(_ input: String, kind: String) -> String {
        let prefix = "(?i)^\\s*\(kind)\\s*:\\s*"
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        var value = trimmed.replacingOccurrences(of: prefix, with: "", options: .regularExpression)
        let pattern = kind == "subreddit" ? "(?i)(?:https?://)?(?:www\\.)?reddit\\.com/r/([^/?#\\s]+)" : "(?i)(?:https?://)?(?:t(?:elegram)?\\.me/)([^/?#\\s]+)"
        if let regex = try? NSRegularExpression(pattern: pattern),
           let match = regex.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)), let range = Range(match.range(at: 1), in: value) { value = String(value[range]) }
        else { value = value.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/")) }
        if kind == "subreddit" && value.lowercased().hasPrefix("r/") { value = String(value.dropFirst(2)) }
        if kind == "channel" && value.hasPrefix("@") { value = String(value.dropFirst()) }
        if value.isEmpty || value.contains(where: { $0.isWhitespace }) { return "" }
        return value.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }
    static func normalizeTags(_ input: String) -> String {
        var seen = Set<String>(); var tags: [String] = []
        // Retain the reference's treatment of a literal 'tags:' prefix.
        for part in input.split(whereSeparator: { $0.isWhitespace || $0 == "," }) {
            let tag = part.hasPrefix("#") ? String(part) : "#" + part
            if seen.insert(tag).inserted { tags.append(tag) }
        }
        return tags.joined(separator: " ")
    }
    static func completeRequest(_ input: String) -> Doc? {
        var lines = input.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        if let first = lines.first, ["/newchannel", "/start"].contains(first.lowercased()) { lines.removeFirst() }
        var data: Doc = [:]
        for line in lines {
            let lower = line.lowercased()
            if lower.hasPrefix("subreddit") { data["subreddit"] = normalize(line, kind: "subreddit") }
            else if lower.hasPrefix("channel") { data["channel"] = normalize(line, kind: "channel") }
            else if lower.hasPrefix("tags") { data["tags"] = normalizeTags(line) }
        }
        if ["subreddit", "channel", "tags"].allSatisfy({ !text(data[$0]).isEmpty }) { return data }
        if lines.count == 3 {
            data = ["subreddit": normalize(lines[0], kind: "subreddit"), "channel": normalize(lines[1], kind: "channel"), "tags": normalizeTags(lines[2])]
            if ["subreddit", "channel", "tags"].allSatisfy({ !text(data[$0]).isEmpty }) { return data }
        }
        return nil
    }
    static func reply(_ app: App, sender: Sender, user: Int64, body: String) throws {
        try app.sender(user, metrics: sender.metrics).sendText(body)
    }
    static func saveChannel(_ app: App, sender: Sender, user: Int64, data: Doc) throws {
        let channel = text(data["channel"]); let subreddit = text(data["subreddit"]); let tags = text(data["tags"])
        let existing = try app.db.one("channels", ["submodule": channel.lowercased()]) != nil
        try app.db.update("channels", ["submodule": channel.lowercased()], ["$set": ["submodule": channel.lowercased(),
            "channel": "@" + channel, "subreddit": subreddit, "tags": tags, "min_upvotes_limit": null,
            "submissions_ranking": "hot", "submissions_limit": 100]], upsert: true)
        try app.db.delete("settings", ["setting": "tech_receiver_state:\(user)"], one: true)
        try reply(app, sender: sender, user: user, body: "\(existing ? "Updated" : "Saved") channel:\nsubreddit: r/\(subreddit)\nchannel: @\(channel)\ntags: \(tags)")
    }
    static func processMessage(_ app: App, sender: Sender, user: Int64, input: String) throws {
        let setting = "tech_receiver_state:\(user)"; let filter: Doc = ["setting": setting]
        let lower = input.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["/help", "help"].contains(lower) { try reply(app, sender: sender, user: user, body: help); return }
        if ["/cancel", "cancel"].contains(lower) {
            try app.db.delete("settings", filter, one: true); try reply(app, sender: sender, user: user, body: "Draft cleared."); return
        }
        if ["/newchannel", "/start"].contains(lower) {
            try app.db.delete("settings", filter, one: true)
            try app.db.update("settings", filter, ["$set": ["data": ["step": "await_subreddit"]]], upsert: true)
            try reply(app, sender: sender, user: user, body: "Send subreddit name or Reddit URL."); return
        }
        if let data = completeRequest(input) { try saveChannel(app, sender: sender, user: user, data: data); return }
        let previous = try app.db.one("settings", filter)
        var state = object(previous?["data"])
        if previous == nil { state = ["step": "await_subreddit"] }
        let response: String
        switch text(state["step"]) {
        case "await_subreddit":
            let subreddit = normalize(input, kind: "subreddit")
            if subreddit.isEmpty { try reply(app, sender: sender, user: user, body: help); return }
            state = ["step": "await_channel", "subreddit": subreddit]
            response = "Saved subreddit: r/\(subreddit)\nNow send channel (@name or t.me link)."
        case "await_channel":
            let channel = normalize(input, kind: "channel")
            if channel.isEmpty { try reply(app, sender: sender, user: user, body: "Channel is invalid. Send @channel_name or https://t.me/channel_name"); return }
            state["step"] = "await_tags"; state["channel"] = channel
            response = "Saved channel: @\(channel)\nNow send tags like #tag1 #tag2 #tag3"
        case "await_tags":
            let tags = normalizeTags(input)
            if tags.isEmpty { try reply(app, sender: sender, user: user, body: "Tags are invalid. Send tags like #tag1 #tag2 #tag3"); return }
            guard let channel = state["channel"] as? String, let subreddit = state["subreddit"] as? String else { throw R2TError.config }
            try saveChannel(app, sender: sender, user: user, data: ["channel": channel, "subreddit": subreddit, "tags": tags]); return
        default:
            try app.db.delete("settings", filter, one: true); try reply(app, sender: sender, user: user, body: help); return
        }
        try app.db.update("settings", filter, ["$set": ["data": state]], upsert: true)
        try reply(app, sender: sender, user: user, body: response)
    }
    static func receiver(_ app: App, sender: Sender) throws -> Supply {
        _ = try app.db.command("createIndexes", "settings", ["indexes": [["key": ["setting": 1], "name": "setting_1", "unique": true]]])
        let record = try app.db.one("settings", ["setting": 1]); var last = integer64(record?["last_update"])
        if record == nil { try app.db.insert("settings", [["setting": 1, "last_update": 0]]) }
        let updates = try sender.api("getUpdates", ["offset": last + 1])
        let configured = object(app.config.values["telegram"])["papa"]
        guard let papa = (configured as? NSNumber)?.int64Value ?? Int64(text(configured)), let items = updates as? [Doc] else { throw R2TError.config }
        for update in items {
            guard update["update_id"] is NSNumber else { throw R2TError.telegram }
            last = max(last, integer64(update["update_id"]))
            let message = object(update["message"])
            guard let id = object(message["chat"])["id"] as? NSNumber, let body = message["text"] as? String, id.int64Value >= 0 else { continue }
            let user = id.int64Value
            try sender.api("forwardMessage", ["chat_id": object(app.config.values["telegram"])["dev_chat"] ?? null,
                "from_chat_id": user, "message_id": message["message_id"] ?? null])
            if user == papa { try processMessage(app, sender: sender, user: user, input: body) }
        }
        try app.db.update("settings", ["setting": 1], ["$set": ["last_update": last]])
        return .stop
    }
}
func commandOutput(_ name: String, _ args: [String]) throws -> String {
    let paths = (ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin").components(separatedBy: ":")
    guard let binary = paths.map({ URL(fileURLWithPath: $0).appendingPathComponent(name) }).first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) else { throw R2TError.io }
    let process = Process(); process.executableURL = binary; process.arguments = args
    let pipe = Pipe(); process.standardOutput = pipe; process.standardError = FileHandle.nullDevice
    try process.run(); let output = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
    guard process.terminationStatus == 0 else { throw R2TError.io }
    return String(decoding: output, as: UTF8.self)
}
