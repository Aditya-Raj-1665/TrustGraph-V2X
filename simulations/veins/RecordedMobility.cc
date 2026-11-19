#include <omnetpp.h>
#include "simu5g/corenetwork/bearerConfigurator/BearerConfigurator.h"
#include "veins_inet/VeinsInetMobility.h"

class SingleCarBearerConfigurator : public simu5g::BearerConfigurator
{
    bool carConfigured = false;

public:
    void configureCar()
    {
        Enter_Method_Silent();
        if (carConfigured)
            return;
        if (!authoredBearers_.empty())
            throw omnetpp::cRuntimeError("Expected an empty bearer table before the only car joins");
        configureDrbs();
        if (static_cast<int>(authoredBearers_.size()) != par("expectedCars").intValue())
            throw omnetpp::cRuntimeError("All configured cars must register in the same initial SUMO step");
        carConfigured = true;
    }
};

Define_Module(SingleCarBearerConfigurator);

class RecordedMobility : public veins::VeinsInetMobility
{
    omnetpp::cOutVector x{"sumoX"};
    omnetpp::cOutVector y{"sumoY"};
    bool bearerConfigured = false;

    void nextPosition(const inet::Coord& position, std::string road,
                      double speed, double angle) override
    {
        Enter_Method_Silent();
        VeinsInetMobility::nextPosition(position, road, speed, angle);
        if (!bearerConfigured) {
            EV_INFO << "TRUSTGRAPH_VEHICLE " << getParentModule()->getFullName()
                    << " " << getExternalId() << "\n";
            auto* configurator = omnetpp::check_and_cast<SingleCarBearerConfigurator*>(
                getSimulation()->getSystemModule()->getSubmodule("bearerConfigurator"));
            configurator->configureCar();
            bearerConfigured = true;
        }
        const auto& current = getCurrentPosition();
        x.record(current.x);
        y.record(current.y);
    }
};

Define_Module(RecordedMobility);
