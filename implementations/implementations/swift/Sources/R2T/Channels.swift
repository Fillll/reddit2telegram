import Foundation

struct Channel {
    let destination: Any
    let subreddit: String
    let ranking: String?
    let limit: Int
    let requiresSubmission: Bool
    let options: Doc
}
enum Channels {
    private static let cacheLock = NSRecursiveLock()
    private static var cachedWeighted: String?
    private static var cachedPromotion: String?
    static func asset(_ name: String) throws -> Doc {
        guard let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Assets") else { throw R2TError.config }
        return object(try parseJSON(Data(contentsOf: url)))
    }
    static func publicModules(_ app: App) throws -> [String] {
        Array(Set(try schedules(app.config).map { $0.1 }.filter { !$0.hasPrefix("tech_") })).sorted()
    }
    static func identity(_ app: App, module: String) throws -> (Any, String) {
        if module == "r_porn" { return ("@r_porn", try weighted()) }
        if module == "reddit2telegram" { return ("@reddit2telegram", "") }
        if let record = try app.db.one("channels", ["submodule": module.lowercased()]) {
            return (record["channel"] ?? null, text(record["subreddit"]))
        }
        guard let record = try asset("local_channels")[module] as? Doc else { throw R2TError.config }
        return (record["t_channel"] ?? null, text(record["subreddit"]))
    }
    static func weighted() throws -> String {
        cacheLock.lock(); defer { cacheLock.unlock() }
        if let cachedWeighted { return cachedWeighted }
        let weights = object(try asset("weighted_channel")["weights"])
        let total = weights.values.reduce(0.0) { $0 + number($1) }
        guard total > 0 else { throw R2TError.config }
        var draw = Double.random(in: 0..<total)
        for name in weights.keys.sorted() {
            let weight = number(weights[name])
            if draw < weight { cachedWeighted = name; return name }
            draw -= weight
        }
        throw R2TError.config
    }
    static func resolve(_ app: App, module: String) throws -> Channel {
        if module == "r_porn" {
            let subreddit = try weighted(); let data = try asset("weighted_channel")
            var options: Doc = ["check_dups": true, "min_upvotes_limit": object(data["limits"])[subreddit] ?? null]
            for kind in ["text", "other", "album", "gif", "img", "video", "gallery"] {
                switch kind {
                case "text": options[kind] = "{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name} → #{subreddit_name}\n{short_link}\n{channel}"
                case "other", "album": options[kind] = "{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name} → #{subreddit_name}\n{short_link}\n{channel}"
                default: options[kind] = "{title}\n\n{upvotes} upvotes\n/r/{subreddit_name} → #{subreddit_name}\n{short_link}\n{channel}"
                }
            }
            return Channel(destination: "@r_porn", subreddit: subreddit, ranking: nil, limit: 100, requiresSubmission: true, options: options)
        }
        if module == "reddit2telegram" {
            let target = try promotionTarget(app); let (_, subreddit) = try identity(app, module: target)
            return Channel(destination: "@reddit2telegram", subreddit: subreddit, ranking: "top", limit: 1000, requiresSubmission: true, options: [:])
        }
        if module.hasPrefix("tech_") {
            let destination: Any
            switch module {
            case "tech_receiver": destination = "@r_channels"
            case "tech_weekly_radar": destination = "@reddit2telegram"
            case "tech_cleaner", "tech_anniversary", "tech_store_stat": destination = object(app.config.values["telegram"])["dev_chat"] ?? null
            default: throw R2TError.config
            }
            return Channel(destination: destination, subreddit: "all", ranking: nil, limit: 100,
                requiresSubmission: !["tech_anniversary", "tech_store_stat"].contains(module), options: [:])
        }
        let record: Doc
        if let result = try app.db.one("channels", ["submodule": module.lowercased()]) { record = result }
        else {
            guard let result = try asset("local_channels")[module] as? Doc else { throw R2TError.config }
            record = ["channel": result["t_channel"] ?? null, "subreddit": result["subreddit"] ?? null,
                "submissions_ranking": result["submissions_ranking"] ?? null, "submissions_limit": result["submissions_limit"] ?? 100]
        }
        var options: Doc = ["min_upvotes_limit": record["min_upvotes_limit"] ?? null]
        for kind in ["text", "gif", "video", "img", "album", "gallery", "other"] {
            if record["content"] == nil || record["content"] is NSNull { options[kind] = true }
            else { options[kind] = object(record["content"])[kind] ?? false }
        }
        let rank = (record["submissions_ranking"] as? String).map { ["hot", "new", "top"].contains($0) ? $0 : "hot" }
        return Channel(destination: record["channel"] ?? null, subreddit: text(record["subreddit"]), ranking: rank,
            limit: (record["submissions_limit"] as? NSNumber)?.intValue ?? Int.max, requiresSubmission: true, options: options)
    }
    static func maintenance(_ app: App, module: String, sender: Sender) throws -> Supply {
        // Kept fail-closed until the durable maintenance/state-machine port is
        // complete; main's full-port guard also blocks all application roles.
        if module == "tech_anniversary" { return try Anniversaries.run(app, sender: sender) }
        throw R2TError.incompletePort
    }
    static func post(_ app: App, module: String, channel: Channel, submission: Doc, sender: Sender, reddit: Reddit) throws -> Supply {
        switch module {
        case "reddit2telegram": return try promotion(app, submission: submission, sender: sender, reddit: reddit)
        case "tech_cleaner": return try Maintenance.cleaner(app, sender: sender)
        case "tech_receiver": return try Maintenance.receiver(app, sender: sender)
        case "tech_weekly_radar": return try Maintenance.weekly(app, sender: sender)
        case "tech_store_stat", "tech_anniversary":
            return try maintenance(app, module: module, sender: sender)
        default: return try sender.simple(submission, options: channel.options, reddit: reddit)
        }
    }
    static func tags(_ app: App, module: String) throws -> String? {
        if let record = try app.db.one("channels", ["submodule": module.lowercased()]),
           let tags = record["tags"] as? String, !tags.isEmpty { return tags }
        let path = app.config.app.appendingPathComponent("channels/\(module)/tags.txt")
        if !FileManager.default.fileExists(atPath: path.path) { return nil }
        return try String(contentsOf: path, encoding: .utf8)
    }
    static func nice(_ app: App, module: String, submission: Doc, sender: Sender, reddit: Reddit,
                     heading: String = "", ending: String = "", channel: String? = nil) throws -> Supply {
        let destination: String
        if let channel { destination = channel }
        else { guard let value = try identity(app, module: module).0 as? String else { throw R2TError.config }; destination = value }
        let tags = try tags(app, module: module)?.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ") ?? ""
        guard submission["created_utc"] is NSNumber else { throw R2TError.config }
        let date = Date(timeIntervalSince1970: number(submission["created_utc"]))
        let formatter = DateFormatter(); formatter.timeZone = TimeZone(secondsFromGMT: 0); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyy MMM dd"
        var options: Doc = ["channel_to_promote": destination, "date": formatter.string(from: date),
            "tags": tags, "extra_ending": ending, "announcement_heading": heading]
        for kind in ["text", "other", "album", "gif", "img", "video", "gallery"] {
            switch kind {
            case "text": options[kind] = "{announcement_heading}{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}"
            case "other", "album": options[kind] = "{announcement_heading}{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}"
            default: options[kind] = "{announcement_heading}{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}"
            }
        }
        return try sender.simple(submission, options: options, reddit: reddit)
    }
    static func updateOrder(_ app: App) throws {
        var order: Doc = [:]
        for module in try publicModules(app) where module != "reddit2telegram" {
            guard let channel = try identity(app, module: module).0 as? String else { throw R2TError.config }
            if let first = try app.db.one("view_with_first_dates", ["_id": channel.lowercased()]), let date = first["first_date"] { order[module] = date }
        }
        try app.db.update("settings", ["setting": "r2t_promotion_queue"],
            ["$setOnInsert": ["already_promoted": [Any](), "counter": 0], "$set": ["promotion_order": order]], upsert: true)
    }
    static func promotionTarget(_ app: App) throws -> String {
        cacheLock.lock(); defer { cacheLock.unlock() }
        if let cachedPromotion { return cachedPromotion }
        let all = try publicModules(app).filter { $0 != "reddit2telegram" }
        let weekday = (Calendar.current.component(.weekday, from: Date()) + 5) % 7
        if weekday == 6 {
            guard let target = all.randomElement() else { throw R2TError.config }
            cachedPromotion = target; return target
        }
        if try app.db.one("settings", ["setting": "r2t_promotion_queue"]) == nil { try updateOrder(app) }
        guard let record = try app.db.one("settings", ["setting": "r2t_promotion_queue"]),
              let promoted = record["already_promoted"] as? [String], let order = record["promotion_order"] as? Doc else { throw R2TError.config }
        let candidates = order.keys.sorted { (bsonDate(order[$0])?.timeIntervalSince1970 ?? 0) > (bsonDate(order[$1])?.timeIntervalSince1970 ?? 0) }
        for name in candidates where all.contains(name) && !promoted.contains(name) { cachedPromotion = name; return name }
        try app.db.update("settings", ["setting": "r2t_promotion_queue"], ["$inc": ["counter": 1], "$set": ["already_promoted": [Any]()]])
        throw R2TError.config
    }
    static func promotion(_ app: App, submission: Doc, sender: Sender, reddit: Reddit) throws -> Supply {
        let current = Date(); let calendar = Calendar.current
        let weekday = (calendar.component(.weekday, from: current) + 5) % 7
        let hour = calendar.component(.hour, from: current)
        if weekday == 5 && [0,23].contains(hour) && calendar.component(.minute, from: current) == 1 { try updateOrder(app); return .stop }
        if weekday == 5 { return .stop }
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyy MMM dd"
        let hash = try digest(formatter.string(from: current), algorithm: "SHA1")
        var selectedHour = 0
        for i in stride(from: 0, to: hash.count, by: 2) {
            let start = hash.index(hash.startIndex, offsetBy: i); let end = hash.index(start, offsetBy: 2)
            guard let byte = Int(hash[start..<end], radix: 16) else { throw R2TError.config }
            selectedHour = (selectedHour * 256 + byte) % 24
        }
        if hour != selectedHour { return .stop }
        let target = try promotionTarget(app)
        let result = try nice(app, module: target, submission: submission, sender: sender, reddit: reddit)
        if result == .sent && weekday < 5 { try app.db.update("settings", ["setting": "r2t_promotion_queue"], ["$push": ["already_promoted": target]]) }
        return result
    }
}
