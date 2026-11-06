#include "queue.hpp"
#include "channels.hpp"
#include <condition_variable>
#include <future>
#include <numbers>
#include <queue>
#include <set>
#include <thread>
namespace r2t {
Sender App::sender(Json destination, Metrics metrics) const {
    return Sender(config, db, std::move(destination), std::move(metrics), videos);
}
void App::run_job(const Json &task) const {
    const auto &args = get(task, "args");
    auto module = text(args, "submodule_name");
    auto created = get(task, "created_at");
    Metrics metrics(config->root, id_string(get(task, "_id")), module,
                    created.is_number() ? std::optional<double>(number(created)) : std::nullopt);
    Json filter = {{"_id", get(task, "_id")}};
    std::optional<Error> outcome;
    try {
        log("Modified " +
            std::to_string(
                db.update("tasks", filter, {{"$set", {{"status", 2}, {"updated_at", now()}}}})) +
            " docs");
        if (text(task, "name") != "supply")
            throw Error(Kind::UnknownTask);
        auto next = config;
        if (get(args, "config").is_object()) {
            auto copy = std::make_shared<Config>(*config);
            copy->values = get(args, "config");
            next = copy;
        } else if (get(args, "config_filename").is_string())
            next = std::make_shared<Config>(text(args, "config_filename"));
        App job(next, get(next->values, "db") == get(config->values, "db") ? db : Database(*next),
                reporter, videos);
        ErrorContext context;
        try {
            job.supply(module, metrics, context);
        } catch (...) {
            auto error = safe_error();
            reporter.capture(error, module);
            try {
                developer(job, module, context, error, metrics);
            } catch (...) {
                log("developer reporting failed for " + module, true);
            }
            throw;
        }
        log("Modified " +
            std::to_string(
                db.update("tasks", filter, {{"$set", {{"status", 3}, {"updated_at", now()}}}})) +
            " docs");
        log("Task supply successfully executed.");
    } catch (...) {
        outcome = safe_error();
        log(std::string("Task supply failed: ") + outcome->what(), true);
        try {
            log("Modified " +
                std::to_string(db.update("tasks", filter,
                                         {{"$set", {{"status", 4}, {"updated_at", now()}}}})) +
                " docs");
        } catch (...) {
            outcome = safe_error();
        }
    }
    metrics.finish(outcome);
}
void App::supply(const std::string &module, Metrics metrics, ErrorContext &context) const {
    long_sleep(.2);
    auto channel = resolve(*this, module);
    context.channel =
        channel.destination.is_string() ? text(channel.destination) : channel.destination.dump();
    if (!channel.requires_submission) {
        auto sender = this->sender(channel.destination, metrics);
        maintenance(*this, module, sender);
        return;
    }
    auto rankings = channel.ranking ? std::vector<std::string>{*channel.ranking}
                                    : std::vector<std::string>{"hot", "new", "top"};
    for (auto &ranking : rankings) {
        context.link.reset();
        Reddit reddit(*config, metrics);
        auto sender = this->sender(channel.destination, metrics);
        std::optional<std::string> after;
        size_t scanned = 0;
        std::optional<Supply> last;
        bool stop = false;
        while (scanned < channel.limit && !stop) {
            int retries = 0;
            Json page;
            while (true)
                try {
                    page = reddit.listing(channel.subreddit, ranking, channel.limit, after);
                    break;
                } catch (...) {
                    if (++retries >= 10)
                        throw;
                    metrics.count("reddit_listing_retries");
                    long_sleep(2.818281828 * std::numbers::pi / 2);
                }
            auto &items = get(get(page, "data"), "children");
            if (!items.is_array())
                throw Error(Kind::Reddit);
            if (items.empty())
                break;
            for (auto &item : items) {
                if (scanned >= channel.limit)
                    break;
                scanned++;
                auto &submission = get(item, "data");
                auto link = "https://redd.it/" + text(submission, "id");
                context.link = link;
                if (sender.was_before(link) || sender.too_many_errors(link))
                    continue;
                auto result = post(*this, module, channel, submission, sender, reddit);
                last = result;
                switch (result) {
                case Supply::Sent:
                    sender.mark(link, true);
                    stop = true;
                    break;
                case Supply::Reject:
                    sender.mark(link, false);
                    break;
                case Supply::Skip:
                    break;
                case Supply::Stop:
                    stop = true;
                    break;
                }
                if (stop)
                    break;
            }
            auto &next = get(get(page, "data"), "after");
            after = next.is_string() ? std::optional<std::string>(text(next)) : std::nullopt;
            if (!after)
                break;
        }
        if (last)
            break;
    }
    context.link.reset();
    clean(*config, channel.destination.is_string() ? text(channel.destination) : "");
}
class Workers {
    std::mutex lock;
    std::condition_variable ready;
    std::queue<std::function<void()>> jobs;
    bool stopping = false;
    std::vector<std::thread> threads;
    std::atomic<size_t> pending{0};

  public:
    explicit Workers(size_t count) {
        try {
            for (size_t i = 0; i < count; i++)
                threads.emplace_back([this] {
                    while (true) {
                        std::function<void()> job;
                        {
                            std::unique_lock guard(lock);
                            ready.wait(guard, [&] { return stopping || !jobs.empty(); });
                            if (jobs.empty() && stopping)
                                return;
                            job = std::move(jobs.front());
                            jobs.pop();
                        }
                        try {
                            job();
                        } catch (...) {
                            log(std::string("Consumer worker failed: ") + safe_error().what(),
                                true);
                        }
                        pending--;
                    }
                });
        } catch (...) {
            drain();
            throw;
        }
    }
    ~Workers() {
        drain();
    }
    size_t size() const {
        return pending.load();
    }
    void submit(std::function<void()> job) {
        {
            std::lock_guard guard(lock);
            jobs.push(std::move(job));
            pending++;
        }
        ready.notify_one();
    }
    void drain() {
        {
            std::lock_guard guard(lock);
            stopping = true;
        }
        ready.notify_all();
        for (auto &thread : threads)
            if (thread.joinable())
                thread.join();
    }
};
void consumer(const App &app) {
    auto &config = *app.config;
    if (!config.workers() || !config.max_pending() || !config.batch_size())
        throw Error(Kind::Config);
    r2t_install_signals();
    auto recovered = app.db.update(
        "tasks",
        {{"status", {{"$in", Json::array({2, 5})}}}, {"updated_at", {{"$lt", now() - 60}}}},
        {{"$set", {{"status", 1}, {"updated_at", now()}}}}, true);
    if (recovered)
        log("Recovered " + std::to_string(recovered) + " abandoned tasks", true);
    log("Starting consumer C++ with " + std::to_string(config.workers()) + " workers");
    Workers workers(config.workers());
    ScopeExit drain([&] {
        log("Stopped claiming tasks; draining " + std::to_string(workers.size()) + " pending jobs");
        workers.drain();
    });
    double next_memory = 0;
    while (!r2t_stopping()) {
        if (now() >= next_memory) {
            next_memory = now() + 60;
            try {
                for (auto &line : split(read_file("/proc/self/status"), "\n"))
                    if (line.starts_with("VmRSS:")) {
                        auto v = words(line);
                        if (v.size() > 1 && std::stoull(v[1]) >= 256 * 1024)
                            r2t_allocator(0, 1);
                        break;
                    }
            } catch (...) {
            }
        }
        auto expired =
            app.db.update("tasks", {{"status", 1}, {"created_at", {{"$lt", now() - 25 * 60}}}},
                          {{"$set", {{"status", 4}, {"updated_at", now()}}}}, true);
        if (expired)
            log("Failed " + std::to_string(expired) + " expired new tasks", true);
        auto size = workers.size();
        auto available = config.max_pending() > size ? config.max_pending() - size : 0;
        auto cutoff = now() - 25 * 60;
        std::vector<Json> batch;
        for (size_t i = 0; i < std::min(available, config.batch_size()); i++) {
            auto task =
                app.db.claim("tasks", {{"status", 1}, {"created_at", {{"$gte", cutoff}}}},
                             {{"$set", {{"status", 5}, {"updated_at", now()}}}},
                             {{"created_at", 1}}, {{"name", 1}, {"args", 1}, {"created_at", 1}});
            if (!task)
                break;
            batch.push_back(*task);
        }
        log("Claimed " + std::to_string(batch.size()) + " new tasks");
        for (auto &task : batch)
            workers.submit([app, task] { app.run_job(task); });
        r2t_wait_stop(5000);
    }
}
std::vector<std::pair<std::string, std::string>> schedules(const Config &config) {
    auto lines = split(read_file(config.cron_path()), "\n");
    std::vector<std::pair<std::string, std::string>> rows;
    for (size_t i = 1; i < lines.size(); i++) {
        if (trim(lines[i]).empty())
            continue;
        auto fields = split(lines[i], "\t");
        if (fields.size() < 2)
            throw Error(Kind::Config);
        rows.emplace_back(fields[0], fields[1]);
    }
    return rows;
}
static bool field(const std::string &expr, int current, int minimum, int maximum) {
    auto parse = [](const std::string &s) {
        static const std::vector<std::string> days = {"sun", "mon", "tue", "wed",
                                                      "thu", "fri", "sat"};
        auto it = std::find(days.begin(), days.end(), lower(s));
        if (it != days.end())
            return int(it - days.begin());
        try {
            size_t n;
            int v = std::stoi(s, &n);
            if (n != s.size())
                throw Error(Kind::Config);
            return v;
        } catch (...) {
            throw Error(Kind::Config);
        }
    };
    bool matches = false;
    for (auto &item : split(expr, ",")) {
        auto parts = split(item, "/");
        if (parts.size() > 2)
            throw Error(Kind::Config);
        auto range = parts[0];
        int step = parts.size() == 2 ? parse(parts[1]) : 1;
        if (step <= 0)
            throw Error(Kind::Config);
        int first, last;
        if (range == "*") {
            first = minimum;
            last = maximum;
        } else {
            auto bounds = split(range, "-");
            if (bounds.size() > 2)
                throw Error(Kind::Config);
            first = parse(bounds[0]);
            last = bounds.size() == 2 ? parse(bounds[1]) : parts.size() == 2 ? maximum : first;
        }
        if (first < minimum || last > maximum || first > last)
            throw Error(Kind::Config);
        for (int n = first; n <= last; n += step)
            matches |= n == current || (maximum == 7 && n == 7 && current == 0);
    }
    return matches;
}
bool cron_matches(const std::string &mask, double date) {
    auto p = words(mask);
    if (p.size() != 5)
        throw Error(Kind::Config);
    auto tm = time_parts(date);
    bool minute = field(p[0], tm.tm_min, 0, 59), hour = field(p[1], tm.tm_hour, 0, 23),
         day = field(p[2], tm.tm_mday, 1, 31), month = field(p[3], tm.tm_mon + 1, 1, 12),
         weekday = field(p[4], tm.tm_wday, 0, 7);
    return minute && hour && month &&
           ((p[2] != "*" && p[4] != "*") ? (day || weekday) : (day && weekday));
}
void scheduler(const App &app) {
    double current = now();
    std::vector<std::string> modules;
    for (auto &[mask, module] : schedules(*app.config))
        if (cron_matches(mask, current))
            modules.push_back(module);
    std::shuffle(modules.begin(), modules.end(), random());
    if (modules.empty())
        return;
    auto created = now();
    std::vector<Json> docs;
    for (auto &module : modules)
        docs.push_back(
            {{"name", "supply"},
             {"args", {{"submodule_name", module}, {"config_filename", app.config->path.string()}}},
             {"status", 1},
             {"created_at", created},
             {"updated_at", created}});
    app.db.insert("tasks", docs);
    auto run = active_run(app.config->root);
    if (run)
        emit(*run, "scheduler_submitted", {{"submitted_jobs", docs.size()}});
    log("Inserted " + std::to_string(docs.size()) + " tasks");
}
} // namespace r2t
