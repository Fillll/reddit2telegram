#pragma once
#include "model.hpp"
namespace r2t {
class App;
class Metrics;
struct ErrorContext {
    std::optional<std::string> channel, link;
};
class Reporter {
    struct Impl;
    std::shared_ptr<Impl> impl;

  public:
    explicit Reporter(const Config &config);
    void capture(const Error &error, const std::string &module) const;
};
void developer(const App &app, const std::string &module, const ErrorContext &context,
               const Error &error, Metrics metrics);
} // namespace r2t
