import Foundation

func utcCalendar() -> Calendar { var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(secondsFromGMT: 0)!; return c }
func dateText(_ date: Date, format: String = "yyyy-MM-dd") -> String {
    let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone(secondsFromGMT: 0); f.dateFormat = format
    return f.string(from: date)
}
func utcDate(_ value: Any?) throws -> Date {
    if let date = bsonDate(value) { return utcCalendar().startOfDay(for: date) }
    if let string = value as? String {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone(secondsFromGMT: 0); f.dateFormat = "yyyy-MM-dd"; f.isLenient = false
        if let date = f.date(from: string), dateText(date) == string { return date }
    }
    throw R2TError.config
}
func htmlEscape(_ value: String) -> String {
    value.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        .replacingOccurrences(of: ">", with: "&gt;").replacingOccurrences(of: "\"", with: "&quot;").replacingOccurrences(of: "'", with: "&#x27;")
}
func chatKey(_ value: Any) -> String { (value as? String)?.lowercased() ?? ((try? json(value)) ?? "") }
func bump(_ record: inout Doc, _ key: String) { record[key] = Int(number(record[key])) + 1 }
func pushError(_ record: inout Doc, _ error: Doc) { var errors = array(record["errors"]); errors.append(error); record["errors"] = errors }

final class Anniversaries {
    static let dateKind = "r2t_anniversary_date"
    static let eventKind = "r2t_anniversary_delivery"
    static let runKind = "r2t_anniversary_run"
    static let lock = "r2t_anniversary_sweep_lock"
    static let main = "@reddit2telegram"
    static let community = "@r_channels"
    let app: App
    let sender: Sender
    let lease: Lease
    init(app: App, sender: Sender) { self.app = app; self.sender = sender; lease = Lease(db: app.db, key: Self.lock) }
    static func messages(channel: String, years: Int, channels: [String], today: Date) -> [String] {
        let plural = years == 1 ? "" : "s"
        var intro = "🌍 <b>Discover the Reddit2Telegram family</b>\n\n📣 @reddit2telegram — our main channel for discovering posts and channels from across the network.\n\n💬 @r_channels — join the community, find new channels, ask questions, and suggest your next favorite.\n\n🎂 <b>Celebrating \(htmlEscape(channel)): \(years) year\(plural) together!</b>\n📅 \(dateText(today, format: "dd MMMM yyyy"))\nThank you for reading, sharing, and being part of the community. Here’s to another year of great discoveries!"
        let excluded = [channel.lowercased(), main, community, "@r_channels_test"]
        let others = Set(channels.map { $0.lowercased() }.filter { !excluded.contains($0) }).sorted()
        if others.isEmpty { return [intro] }
        intro += "\n\n🧭 Explore more of our channels in the directory below."
        var pages: [String] = []; var lines: [String] = []
        for (index, channel) in others.enumerated() {
            let line = "\(index + 1). \(htmlEscape(channel))"
            let candidate = (lines + [line]).joined(separator: "\n")
            if !lines.isEmpty && (lines.count == 100 || candidate.utf16.count > 3400) { pages.append(lines.joined(separator: "\n")); lines = [] }
            lines.append(line)
        }
        if !lines.isEmpty { pages.append(lines.joined(separator: "\n")) }
        return [intro] + pages.enumerated().map { "🧭 <b>More channels · \($0.offset + 1)/\(pages.count)</b>\n\n\($0.element)" }
    }
    func birthday(_ channel: String, record: Doc?) throws -> Date? {
        let id = Self.dateKind + ":" + channel
        let cached = try app.db.one("settings", ["_id": id])
        let explicit = record?["anniversary_date"]
        let hasExplicit = explicit != nil && !(explicit is NSNull)
        let birthday: Date; let source: String
        if hasExplicit { birthday = try utcDate(explicit); source = "explicit" }
        else if let cached { return try utcDate(cached["date"]) }
        else {
            let docs = try app.db.find("urls", ["channel": channel, "sent": true, "ts": ["$type": "date"]], sort: ["ts": 1], limit: 1, projection: ["ts": 1])
            guard let first = docs.first else { return nil }
            birthday = try utcDate(first["ts"]); source = "first_sent_post"
        }
        let values: Doc = ["setting": id, "kind": Self.dateKind, "channel": channel, "date": dateBSON(birthday), "source": source]
        try app.db.update("settings", ["_id": id], [hasExplicit ? "$set" : "$setOnInsert": values], upsert: true)
        return birthday
    }
    func inventory() throws -> ([(String, Date)], [String], [Doc]) {
        let local = try Channels.asset("local_channels")
        let handles = try NSRegularExpression(pattern: "^@[a-zA-Z][a-zA-Z0-9_]{4,31}$")
        var channels: [(String, Date)] = []; var seen = Set<String>(); var skipped: [String] = []; var errors: [Doc] = []
        for module in try Channels.publicModules(app) {
            try lease.renew()
            do {
                let record = try app.db.one("channels", ["submodule": module])
                let channel: String
                if let record { guard let handle = record["channel"] as? String else { continue }; channel = handle }
                else { guard let handle = object(local[module])["t_channel"] as? String else { throw R2TError.config }; channel = handle }
                if handles.firstMatch(in: channel, range: NSRange(channel.startIndex..., in: channel)) == nil { continue }
                let key = channel.lowercased()
                if [Self.community, "@r_channels_test"].contains(key) || seen.contains(key) { continue }
                if let date = try birthday(key, record: record) { seen.insert(key); channels.append((key, date)) }
                else { log("Anniversary skipped: \(key) has no successful posting history", warning: true); skipped.append(key) }
            } catch { errors.append(["submodule": module, "error_type": safeError(error).description]) }
        }
        return (channels, skipped, errors)
    }
    func queue(channel: String, years: Int, today: Date, channels: [String]) throws {
        let year = utcCalendar().component(.year, from: today)
        let id = "\(Self.eventKind):\(channel):\(year)"; let plural = years == 1 ? "" : "s"
        let notice = "🎂 <b>Celebrating \(htmlEscape(channel)): \(years) year\(plural) together!</b>\n📅 \(dateText(today, format: "dd MMMM yyyy"))\n\nDiscover this channel and more in our main feed @reddit2telegram.\nJoin @r_channels to explore the network and meet the community."
        var deliveries: [Doc] = Self.messages(channel: channel, years: years, channels: channels, today: today).map { ["destination": channel, "text": $0, "state": "pending"] }
        var destinations = Set([channel.lowercased()])
        let extra: [Any] = [Self.main, Self.community, object(app.config.values["telegram"])["dev_chat"] ?? null]
        for destination in extra where destinations.insert(chatKey(destination)).inserted { deliveries.append(["destination": destination, "text": notice, "state": "pending"]) }
        try app.db.update("settings", ["_id": id], ["$setOnInsert": ["setting": id, "kind": Self.eventKind,
            "channel": channel, "year": year, "years": years, "anniversary": dateText(today), "created_at": dateBSON(), "complete": false, "deliveries": deliveries]], upsert: true)
    }
    func deliver(_ event: Doc) throws -> Bool {
        guard let id = event["_id"], let deliveries = event["deliveries"] as? [Doc] else { throw R2TError.config }
        var blocked = Set<String>()
        for (index, delivery) in deliveries.enumerated() {
            try lease.renew()
            guard let destination = delivery["destination"], let state = delivery["state"] as? String else { throw R2TError.config }
            let blockedKey = try json(destination); let path = "deliveries.\(index)"
            if state == "sent" || blocked.contains(blockedKey) { continue }
            if ["sending", "uncertain"].contains(state) {
                try app.db.update("settings", ["_id": id, path + ".state": "sending"], ["$set": [path + ".state": "uncertain"]])
                blocked.insert(blockedKey); continue
            }
            let attempt = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
            let response = try app.db.command("update", "settings", ["updates": [["q": ["_id": id, path + ".state": "pending"],
                "u": ["$set": [path + ".state": "sending", path + ".attempt": attempt, path + ".attempted_at": dateBSON()], "$inc": [path + ".attempts": 1]], "multi": false, "upsert": false]]])
            if number(response["n"]) == 0 { blocked.insert(blockedKey); continue }
            let selector: Doc = ["_id": id, path + ".attempt": attempt]
            let checkpoint = Checkpoint(db: app.db, selector: selector, mode: .anniversary(path), ids: [])
            let sender = Sender(copy: self.sender, destination: destination); sender.acknowledgement = checkpoint
            do {
                guard let body = delivery["text"] as? String else { throw R2TError.config }
                guard try sender.sendText(body, preview: true, parse: "HTML") == .sent, !checkpoint.ids.isEmpty else { throw R2TError.announcement }
            } catch {
                if !checkpoint.ids.isEmpty { try checkpoint.record([]) }
                else {
                    let category = safeError(error); let retryable: Bool
                    switch category { case .rejected, .forbidden, .rateLimit: retryable = true; default: retryable = false }
                    try app.db.update("settings", selector, ["$set": [path + ".state": retryable ? "pending" : "uncertain", path + ".last_error_type": category.description]])
                }
                blocked.insert(blockedKey)
            }
            shortSleep()
        }
        guard let current = try app.db.one("settings", ["_id": id]), let parts = current["deliveries"] as? [Doc] else { throw R2TError.config }
        let complete = parts.allSatisfy { text($0["state"]) == "sent" }
        try app.db.update("settings", ["_id": id], ["$set": ["complete": complete, "updated_at": dateBSON()]])
        return complete
    }
    func sweep(_ run: inout Doc, acquired: inout Bool) throws {
        acquired = try lease.acquire()
        if !acquired { run["status"] = "skipped_overlap"; return }
        if let previous = lease.previousOwner {
            try app.db.update("settings", ["kind": Self.runKind, "owner": previous, "status": "running", "_id": ["$ne": run["_id"] ?? null]],
                ["$set": ["status": "interrupted", "finished_at": dateBSON(), "errors": [["error_type": "InterruptedSweep"]]]], multi: true)
        }
        let (channels, skipped, errors) = try inventory(); let names = channels.map { $0.0 }
        run["channels"] = channels.count; run["skipped_no_history"] = skipped; run["errors"] = errors
        let today = try utcDate(run["date"]); let calendar = utcCalendar()
        let todayParts = calendar.dateComponents([.year, .month, .day], from: today)
        guard let year = todayParts.year else { throw R2TError.config }
        for (channel, birthday) in channels {
            try lease.renew()
            let parts = calendar.dateComponents([.year, .month, .day], from: birthday)
            guard let startYear = parts.year, let month = parts.month, var day = parts.day else { throw R2TError.config }
            if month == 2 && day == 29 && !(year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)) { day = 28 }
            let years = year - startYear
            if years > 0 && todayParts.month == month && todayParts.day == day { bump(&run, "due"); try queue(channel: channel, years: years, today: today, channels: names) }
        }
        for event in try app.db.find("settings", ["kind": Self.eventKind, "complete": false]) {
            try lease.renew()
            guard let channel = event["channel"] as? String else { throw R2TError.config }
            if !names.contains(channel) { continue }
            do { if try deliver(event) { bump(&run, "completed") } }
            catch { pushError(&run, ["event": event["_id"] ?? null, "error_type": safeError(error).description]) }
        }
        for event in try app.db.find("settings", ["kind": Self.eventKind, "complete": false]) {
            bump(&run, "pending")
            guard let parts = event["deliveries"] as? [Doc] else { throw R2TError.config }
            for part in parts where ["sending", "uncertain"].contains(text(part["state"])) { bump(&run, "uncertain_messages") }
        }
        run["status"] = number(run["pending"]) > 0 || !array(run["errors"]).isEmpty ? "partial" : "success"
    }
    static func run(_ app: App, sender: Sender) throws -> Supply {
        let service = Anniversaries(app: app, sender: sender)
        let id = runKind + ":" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        var run: Doc = ["_id": id, "kind": runKind, "setting": id, "owner": service.lease.owner,
            "date": dateText(Date()), "started_at": dateBSON(), "status": "running", "channels": 0, "due": 0,
            "completed": 0, "pending": 0, "uncertain_messages": 0, "skipped_no_history": [Any](), "errors": [Any]()]
        try app.db.insert("settings", [run])
        var acquired = false; var outcome: Error?
        do { try service.sweep(&run, acquired: &acquired) }
        catch { outcome = error; run["status"] = "failed"; pushError(&run, ["error_type": safeError(error).description]) }
        run["finished_at"] = dateBSON(); var values = run; values.removeValue(forKey: "_id")
        do { try app.db.update("settings", ["_id": id], ["$set": values]) } catch { if outcome == nil { outcome = error } }
        if acquired { do { try service.lease.release() } catch { if outcome == nil { outcome = error } } }
        if let outcome { throw outcome }
        if ["failed", "partial"].contains(text(run["status"])) { throw R2TError.announcement }
        return .stop
    }
}
