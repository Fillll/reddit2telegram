#pragma once
#include "reporting.hpp"
#include "sender.hpp"
namespace r2t {
class App {
  public:
    std::shared_ptr<const Config> config;
    Database db;
    Reporter reporter;
    std::shared_ptr<std::counting_semaphore<2>> videos;
    App(std::shared_ptr<const Config> config, Database db, Reporter reporter,
        std::shared_ptr<std::counting_semaphore<2>> videos =
            std::make_shared<std::counting_semaphore<2>>(2))
        : config(std::move(config)), db(std::move(db)), reporter(std::move(reporter)),
          videos(std::move(videos)) {}
    Sender sender(Json destination, Metrics metrics) const;
    void run_job(const Json &task) const;
    void supply(const std::string &module, Metrics metrics, ErrorContext &context) const;
};
void consumer(const App &app);
void scheduler(const App &app);
std::vector<std::pair<std::string, std::string>> schedules(const Config &config);
bool cron_matches(const std::string &mask, double date);
} // namespace r2t
