#include "reporting.hpp"
#include "build_info.hpp"
#include "queue.hpp"
#include <condition_variable>
#include <queue>
#include <thread>
namespace r2t {
struct Reporter::Impl {
    struct State {
        std::mutex lock;
        std::condition_variable ready, done;
        std::queue<Json> queue;
        bool stop = false, finished = false;
        std::string dsn, endpoint;
    };
    std::shared_ptr<State> state;
    std::thread worker;
    explicit Impl(const Config &config) {
        auto dsn = text(config.values, "sentry");
        if (dsn.empty())
            return;
        auto url = parse_url(dsn);
        auto parts = split(trim(url.path, "/"), "/");
        if (url.user.empty() || parts.empty() || parts.back().empty())
            throw Error(Kind::Config);
        auto project = parts.back();
        parts.pop_back();
        state = std::make_shared<State>();
        state->dsn = dsn;
        state->endpoint = url.scheme + "://" + url.host + (url.port.empty() ? "" : ":" + url.port) +
                          "/" + (parts.empty() ? "" : join(parts, "/") + "/") + "api/" + project +
                          "/envelope/";
        worker = std::thread([state = state] {
            while (true) {
                Json event;
                {
                    std::unique_lock guard(state->lock);
                    state->ready.wait(guard, [&] { return state->stop || !state->queue.empty(); });
                    if (state->stop && state->queue.empty())
                        break;
                    event = std::move(state->queue.front());
                    state->queue.pop();
                }
                try {
                    auto body = event.dump();
                    auto envelope =
                        Json{{"event_id", get(event, "event_id")}, {"dsn", state->dsn}}.dump() +
                        "\n" + Json{{"type", "event"}, {"length", body.size()}}.dump() + "\n" +
                        body + "\n";
                    Http http;
                    http.request("POST", state->endpoint,
                                 {{"Content-Type", "application/x-sentry-envelope"}}, envelope);
                } catch (...) {
                    log(std::string("Sentry reporting failed: ") + safe_error().what(), true);
                }
            }
            {
                std::lock_guard guard(state->lock);
                state->finished = true;
            }
            state->done.notify_all();
        });
    }
    ~Impl() {
        if (!state)
            return;
        bool finished;
        {
            std::unique_lock guard(state->lock);
            state->stop = true;
            state->ready.notify_all();
            finished = state->done.wait_for(guard, std::chrono::seconds(2),
                                            [&] { return state->finished; });
            if (!finished) {
                std::queue<Json> empty;
                state->queue.swap(empty);
            }
        }
        if (worker.joinable()) {
            if (finished)
                worker.join();
            else
                worker.detach();
        }
    }
};
Reporter::Reporter(const Config &config) : impl(std::make_shared<Impl>(config)) {}
void Reporter::capture(const Error &error, const std::string &module) const {
    auto state = impl->state;
    if (!state)
        return;
    std::lock_guard guard(state->lock);
    if (state->stop || state->queue.size() >= 30)
        return;
    state->queue.push(
        {{"event_id", uuid()},
         {"timestamp", now()},
         {"platform", "other"},
         {"level", "error"},
         {"logger", "r2t-cpp"},
         {"release", build::version},
         {"exception",
          {{"values", Json::array({{{"type", error.what()}, {"value", error.what()}}})}}},
         {"extra", {{"submodule", module}}}});
    state->ready.notify_one();
}
void developer(const App &app, const std::string &module, const ErrorContext &context,
               const Error &error, Metrics metrics) {
    auto sender = app.sender(get(get(app.config->values, "telegram"), "dev_chat"), metrics);
    auto channel = context.channel.value_or(sender.channel());
    Json filter;
    std::string link_title;
    if (context.link) {
        filter = {{"channel", lower(channel)}, {"url", lower(*context.link)}};
        link_title = "link: " + *context.link + "\n";
    } else
        filter = {{"channel", lower(channel)},
                  {"link", "_NO_"},
                  {"date", time_format(now(), "%Y-%m-%d")}};
    auto record =
        app.db.claim("errors", filter, {{"$inc", {{"cnt", 1}}}, {"$set", {{"ts", bson_date()}}}},
                     Json::object(), {{"cnt", 1}, {"_id", 0}}, true);
    if (!record)
        throw Error(Kind::Database);
    auto title = "submodule: " + module + "\nchannel: " + channel + "\n" + link_title +
                 "error_cnt: " + std::to_string(integer(get(*record, "cnt")));
    sender.send_text("<b>r2t error</b>\n" + title + "\n\n\n<pre>" + error.what() + "</pre>", false,
                     "HTML");
}
} // namespace r2t
