#include <open62541/server.h>
/* In 1.3.x UA_Server_new() is declared in server_config_default.h, not in
 * server.h - see the comment at server.h:346. It moved into server.h in 1.4. */
#include <open62541/server_config_default.h>

#include <stdio.h>

/* UA_Server_new() already installs the default configuration, so no separate
 * UA_ServerConfig_setDefault() call is needed here. */
int main(void) {
    UA_Server *server = UA_Server_new();
    if(!server) {
        printf("UA_Server_new() returned NULL\n");
        return 1;
    }

    /* UA_Server_delete() returns void in 1.3.x; it returns UA_StatusCode in 1.4. */
    UA_Server_delete(server);

    printf("open62541-logicmelt test_package OK\n");
    return 0;
}
