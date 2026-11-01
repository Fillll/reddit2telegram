#pragma once
#include "channels.hpp"
namespace r2t {
Supply cleaner(const App &app, Sender &sender);
Supply weekly(const App &app, Sender &sender);
Supply receiver(const App &app, Sender &sender);
std::vector<std::string> public_channels(const App &app, const Sender &sender);
} // namespace r2t
