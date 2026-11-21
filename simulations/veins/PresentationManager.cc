#include <chrono>
#include <csignal>
#include <iostream>
#include <thread>

#ifndef _WIN32
#include <poll.h>
#include <unistd.h>
#endif

#include "veins/modules/mobility/traci/TraCICommandInterface.h"
#include "veins/modules/mobility/traci/TraCIConstants.h"
#include "veins_inet/VeinsInetManagerForker.h"

class PresentationManager : public veins::VeinsInetManagerForker
{
    void finish() override
    {
        if (par("holdFinalFrame").boolValue() && isConnected())
            holdFinalFrame();
        VeinsInetManagerForker::finish();
    }

    void holdFinalFrame()
    {
        std::cout << "Holding final SUMO frame until the GUI closes." << std::endl;
#ifdef SIGPIPE
        // Veins uses plain send(). Treat a closed GUI socket as an error
        // return instead of letting a signal terminate the completed run.
        auto previousSigpipe = std::signal(SIGPIPE, SIG_IGN);
#endif
        try {
            while (true) {
#ifndef _WIN32
                pollfd input{STDIN_FILENO, POLLIN, 0};
                if (poll(&input, 1, 0) > 0 && (input.revents & POLLIN)) {
                    std::string line;
                    if (std::getline(std::cin, line)) {
                        connection->query(veins::TraCIConstants::CMD_CLOSE);
                        break;
                    }
                }
#endif
                // Query display state without advancing SUMO simulation time.
                getCommandInterface()->getPoiIds();
                std::this_thread::sleep_for(std::chrono::milliseconds(250));
            }
        }
        catch (const omnetpp::cRuntimeError&) {
            // The GUI may disconnect before replying to CMD_CLOSE.
        }
        // Veins normally sends CMD_CLOSE in its destructor.
        commandIfc.reset();
        connection.reset();
#ifdef SIGPIPE
        if (previousSigpipe != SIG_ERR)
            std::signal(SIGPIPE, previousSigpipe);
#endif
    }
};

Define_Module(PresentationManager);
