#ifndef R2T_C_MAINTENANCE_H
#define R2T_C_MAINTENANCE_H
#include "channels.h"
bool maintenance_cleaner(const App *app, Sender *sender, Supply *result, Error *error);
bool maintenance_weekly(const App *app, Sender *sender, Supply *result, Error *error);
bool maintenance_receiver(const App *app, Sender *sender, Supply *result, Error *error);
json_t *public_channels(const App *app, Sender *sender, Error *error);
#endif
