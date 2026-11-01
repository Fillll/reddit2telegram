import Foundation

private struct SweepTotals { var channels = 0; var members = 0; var admins = 0; var errors = 0; var previous = 0 }
private struct SubscriberSnapshot { let channel: String; let before: Int; let current: Int }
final class Achievements {
    static let main = "@reddit2telegram"
    static let eventKind = "r2t_achievement_delivery"
    static let history = "r2t_achievements"
    static let lock = "r2t_achievement_sweep_lock"
    let app: App
    let sender: Sender
    let lease: Lease
    init(app: App, sender: Sender) { self.app = app; self.sender = sender; lease = Lease(db: app.db, key: Self.lock) }
    func queue(module: String, channel: String, achievement: Int64) throws {
        let channel = channel.lowercased()
        if let legacy = try app.db.one("settings", ["setting": Self.history]), let raw = legacy["channels"] {
            guard let channels = raw as? Doc else { throw R2TError.config }
            if let previous = channels[channel] {
                let ids = try identifiers(["ids": previous], "ids")
                if ids.contains(achievement) { return }
            }
        }
        let id = "\(Self.eventKind):\(channel):\(achievement)"
        try app.db.update("settings", ["_id": id], ["$setOnInsert": ["setting": id, "kind": Self.eventKind,
            "submodule": module, "channel": channel, "achievement": achievement, "complete": false,
            "message_ids": [Int64](), "forwarded_ids": [Int64](), "created_at": dateBSON()]], upsert: true)
    }
    func candidate(_ event: Doc, checkpoint: Checkpoint, postingAttempted: inout Bool) throws {
        guard let module = event["submodule"] as? String, let channel = event["channel"] as? String else { throw R2TError.config }
        let source = try Channels.resolve(app, module: module)
        let number = try identifiers(["ids": [event["achievement"] ?? null]], "ids")[0]
        let heading = "🏆 Great achievement!\n\(channel)\n💪 Milestone of \(number) subscribers.\n\n"
        let reddit = try Reddit(config: app.config, metrics: sender.metrics)
        let sender = try app.sender(Self.main, metrics: self.sender.metrics); sender.acknowledgement = checkpoint
        var scanned = 0; var after: String?; var stop = false
        while scanned < 1000 && !stop {
            var page: Doc; var retries = 0
            while true {
                do { page = try reddit.listing(subreddit: source.subreddit, ranking: "top", limit: 1000, after: after); break }
                catch {
                    retries += 1; if retries >= 10 { throw error }
                    self.sender.metrics.count("reddit_listing_retries"); longSleep(2.818281828 * Double.pi / 2)
                }
            }
            guard let items = object(page["data"])["children"] as? [Doc] else { throw R2TError.reddit }
            if items.isEmpty { break }
            for item in items {
                if scanned >= 1000 { break }; scanned += 1
                let submission = object(item["data"]); let link = "https://redd.it/" + text(submission["id"])
                if try sender.wasBefore(link) || sender.tooManyErrors(link) { continue }
                postingAttempted = true
                var result = try Channels.nice(app, module: module, submission: submission, sender: sender, reddit: reddit, heading: heading, channel: channel)
                if !checkpoint.ids.isEmpty && result != .sent { result = .stop }
                switch result {
                case .sent: try sender.mark(link, sent: true); stop = true
                case .reject: try sender.mark(link, sent: false)
                case .skip: break
                case .stop: stop = true
                }
                if stop { break }
            }
            after = object(page["data"])["after"] as? String
            if after == nil { break }
        }
    }
    func deliver(_ event: Doc) throws {
        try lease.renew()
        guard let id = event["_id"], let channel = event["channel"] as? String else { throw R2TError.config }
        let selector: Doc = ["_id": id]
        let number = try identifiers(["ids": [event["achievement"] ?? null]], "ids")[0]
        try app.db.update("settings", selector, ["$inc": ["attempts": 1], "$set": ["last_attempt_at": dateBSON()]])
        let checkpoint = try Checkpoint(db: app.db, selector: selector, mode: .achievement, ids: identifiers(event, "message_ids"))
        if checkpoint.ids.isEmpty {
            var attempted = false
            do { try candidate(event, checkpoint: checkpoint, postingAttempted: &attempted) }
            catch { if checkpoint.ids.isEmpty && attempted { throw error } }
            if checkpoint.ids.isEmpty {
                let sender = try app.sender(Self.main, metrics: self.sender.metrics); sender.acknowledgement = checkpoint
                let result = try sender.sendText("🏆 Great achievement!\n\(channel)\n💪 Milestone of \(number) subscribers.")
                if result != .sent || checkpoint.ids.isEmpty { throw R2TError.announcement }
            }
        }
        try lease.renew()
        let ids = checkpoint.ids
        try app.db.update("settings", selector, ["$addToSet": ["message_ids": ["$each": ids]]])
        try app.db.update("settings", ["setting": Self.history], ["$addToSet": ["channels." + channel: number]], upsert: true)
        if channel != Self.main {
            let forwarded = try identifiers(event, "forwarded_ids")
            let sender = try app.sender(channel, metrics: self.sender.metrics)
            for id in ids where !forwarded.contains(id) {
                try lease.renew()
                try sender.api("forwardMessage", ["chat_id": channel, "from_chat_id": Self.main, "message_id": id])
                try app.db.update("settings", selector, ["$addToSet": ["forwarded_ids": id]])
            }
        }
        try app.db.update("settings", selector, ["$set": ["complete": true, "completed_at": dateBSON()]])
    }
    private func report(_ body: String, parse: String? = nil) { _ = try? sender.sendText(body, parse: parse) }
    func sweep() throws -> Supply {
        report("Regular bypass started.")
        guard let url = Bundle.module.url(forResource: "milestones", withExtension: "json", subdirectory: "Assets") else { throw R2TError.config }
        let thresholds = try identifiers(["ids": parseJSON(Data(contentsOf: url))], "ids")
        var modules = try Channels.publicModules(app); let coefficient = 2000.0 / 3 / 2 / Double(max(1, modules.count)); modules.shuffle()
        var seen = Set<String>(); var totals = SweepTotals(); var snapshots: [SubscriberSnapshot] = []
        for module in modules {
            try lease.renew(); shortSleep(coefficient)
            let channel: String
            do {
                let resolved = try Channels.resolve(app, module: module)
                guard let name = resolved.destination as? String, name.hasPrefix("@"), seen.insert(name.lowercased()).inserted else { continue }
                channel = name
            } catch { totals.errors += 1; continue }
            var snapshot: Doc = ["channel": channel.lowercased(), "ts": dateBSON(), "submodule": module]
            totals.channels += 1
            do {
                let response = try sender.api("getChatAdministrators", ["chat_id": channel])
                guard let admins = response as? [Doc] else { throw R2TError.telegram }
                var names: [String] = []
                for admin in admins {
                    if let name = object(admin["user"])["username"] as? String { if name != "reddit2telegram_bot" { names.append("@" + name) } }
                    else { names.append("%NO_USERNAME%") }
                }
                totals.admins += names.count; snapshot["admins"] = names
            } catch { totals.errors += 1; report("Failed to get admins for \(channel).") }
            shortSleep(coefficient)
            do {
                let raw = try sender.api("getChatMemberCount", ["chat_id": channel])
                let members = Int(try identifiers(["ids": [raw]], "ids")[0])
                let previous = try app.db.one("stats", ["channel": channel.lowercased(), "members_cnt": ["$gte": 0]], sort: ["ts": -1])
                let before = try previous.map { Int(try identifiers(["ids": [$0["members_cnt"] ?? null]], "ids")[0]) } ?? members
                for threshold in thresholds where before < threshold && threshold <= members { try queue(module: module, channel: channel, achievement: threshold) }
                snapshot["members_cnt"] = members; try app.db.insert("stats", [snapshot])
                totals.members += members; totals.previous += before
                snapshots.append(SubscriberSnapshot(channel: channel, before: before, current: members))
            } catch { totals.errors += 1; report("Failed to collect statistics or queue milestones for \(channel).") }
        }
        for event in try app.db.find("settings", ["kind": Self.eventKind, "complete": false]) {
            try lease.renew()
            do { try deliver(event) }
            catch {
                totals.errors += 1
                guard let id = event["_id"], let channel = event["channel"] as? String else { throw R2TError.config }
                let number = try identifiers(["ids": [event["achievement"] ?? null]], "ids")[0]
                try app.db.update("settings", ["_id": id], ["$set": ["last_error_type": safeError(error).description, "last_failure_at": dateBSON()]])
                report("Milestone delivery pending: \(channel), \(number) subscribers.")
            }
        }
        let difference = totals.members - totals.previous; let symbol = Self.sign(difference)
        let percentage = totals.previous == 0 ? "0" : Self.round2(Double(difference) / Double(totals.previous) * 100)
        report("Ok, regular bypass results.\n\n<pre>Active channels: \(totals.channels).</pre>\n<pre>Subscribers: \(totals.members).</pre>\n<pre>Cnt diff: \(symbol)\(difference) (\(symbol)\(percentage)%).</pre>\n<pre>Admins: \(totals.admins).</pre>\n<pre>Errors during bypass: \(totals.errors).</pre>\n\n<i>See you!</i>", parse: "HTML")
        shortSleep(); snapshots.sort { $0.current - $0.before > $1.current - $1.before }
        report(Self.leaderboard("📈 <b>TOP 5 GAIN</b> 📈\n", snapshots), parse: "HTML")
        shortSleep(); snapshots.sort { $0.current - $0.before < $1.current - $1.before }
        report(Self.leaderboard("📉 <b>TOP 5 FALL</b> 📉\n", snapshots), parse: "HTML")
        return .stop
    }
    private static func sign(_ value: Int) -> String { value < 0 ? "" : (value == 0 ? "±" : "+") }
    private static func round2(_ value: Double) -> String {
        var s = String(format: "%.2f", value)
        while s.hasSuffix("0") { s.removeLast() }
        if s.hasSuffix(".") { s += "0" }; return s
    }
    private static func leaderboard(_ heading: String, _ snapshots: [SubscriberSnapshot]) -> String {
        var body = heading
        for record in snapshots.prefix(5) {
            let difference = record.current - record.before; let symbol = sign(difference)
            let percentage = record.before == 0 ? "0" : round2(Double(difference) / Double(record.before) * 100)
            body += "\(record.channel): \(record.before) \(symbol)\(difference) (\(symbol)\(percentage)%) → \(record.current)\n"
        }
        return body
    }
    static func run(_ app: App, sender: Sender) throws -> Supply {
        let service = Achievements(app: app, sender: sender)
        if try !service.lease.acquire() { return .stop }
        let outcome: Result<Supply, Error>
        do { outcome = .success(try service.sweep()) } catch { outcome = .failure(error) }
        let released: Result<Void, Error>
        do { try service.lease.release(); released = .success(()) } catch { released = .failure(error) }
        let value = try outcome.get(); try released.get(); return value
    }
}
