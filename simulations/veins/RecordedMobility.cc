#include <cmath>
#include <omnetpp.h>
#include "simu5g/corenetwork/bearerConfigurator/BearerConfigurator.h"
#include "simu5g/stack/rrc/ConnectionControlUe.h"
#include "veins/modules/mobility/traci/TraCICommandInterface.h"
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

class RecordedMobility : public veins::VeinsInetMobility, public omnetpp::cListener
{
    omnetpp::cOutVector x{"sumoX"};
    omnetpp::cOutVector y{"sumoY"};
    omnetpp::cOutVector shown{"displayedServingCell"};
    omnetpp::cOutVector shownSource{"displayedTrustGraphHandover"};
    bool bearerConfigured = false;
    simu5g::ConnectionControlUe* radio = nullptr;
    int displayedCell = 0;
    int handoverAttribution = -1;

    void drawServingLink(int cell, const veins::TraCIColor* newColor = nullptr)
    {
        auto* traci = getCommandInterface();
        const auto link = "serving-link-" + getExternalId();
        if (newColor && displayedCell > 0)
            traci->polygon(link).remove(14);
        if (cell <= 0)
            return;
        auto tower = traci->poi("gnb" + std::to_string(cell)).getPosition();
        const auto car = getCurrentPosition();
        const double length = std::hypot(tower.x - car.x, tower.y - car.y);
        const double dx = length > 0 ? (tower.y - car.y) * 1.5 / length : 0;
        const double dy = length > 0 ? (car.x - tower.x) * 1.5 / length : 0;
        const std::list<veins::Coord> shape{{car.x + dx, car.y + dy, 0},
            {tower.x + dx, tower.y + dy, 0}, {tower.x - dx, tower.y - dy, 0},
            {car.x - dx, car.y - dy, 0}, {car.x + dx, car.y + dy, 0}};
        if (newColor)
            traci->addPolygon(link, "Serving cell", *newColor, true, 14, shape);
        else
            traci->polygon(link).setShape(shape);
    }

    void updateCell(int cell)
    {
        if (cell == displayedCell)
            return;
        const veins::TraCIColor color = cell == 1 ? veins::TraCIColor(35, 125, 255, 255)
            : cell == 2 ? veins::TraCIColor(255, 125, 32, 255)
            : cell == 3 ? veins::TraCIColor(120, 65, 205, 255)
            : cell == 4 ? veins::TraCIColor(0, 145, 95, 255) : veins::TraCIColor(128, 128, 128, 255);
        auto* traci = getCommandInterface();
        traci->vehicle(getExternalId()).setColor(color);
        drawServingLink(cell, &color);
        if (displayedCell > 0 && cell > 0) {
            if (handoverAttribution >= 0)
                shownSource.record(handoverAttribution);
            if (par("captureHandover").boolValue())
                traci->guiView("View #0").takeScreenshot("campus-handover.png");
        }
        shown.record(cell);
        displayedCell = cell;
        handoverAttribution = -1;
    }

    void receiveSignal(omnetpp::cComponent*, omnetpp::simsignal_t signal, omnetpp::intval_t value,
                       omnetpp::cObject*) override
    {
        if (signal == registerSignal("trustGraphAttribution"))
            handoverAttribution = value;
        else
            updateCell(value);
    }

    void finish() override
    {
        if (radio) {
            radio->unsubscribe("servingCell", this);
            radio->unsubscribe("trustGraphAttribution", this);
        }
        VeinsInetMobility::finish();
    }

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
            if (par("showServingCell").boolValue()) {
                radio = omnetpp::check_and_cast<simu5g::ConnectionControlUe*>(getParentModule()->getModuleByPath(
                    ".cellularNic.rrc.nrConnectionControl"));
                radio->subscribe("servingCell", this);
                radio->subscribe("trustGraphAttribution", this);
                if (par("captureHandover").boolValue())
                    getCommandInterface()->guiView("View #0").setScheme("TrustGraph demo");
                updateCell(simu5g::num(radio->getServingNodeId()));
            }
            bearerConfigured = true;
        }
        else if (displayedCell > 0) {
            drawServingLink(displayedCell);
            if (par("captureHandover").boolValue() && getParentModule()->getIndex() == 0 && simTime() == 4)
                getCommandInterface()->guiView("View #0").takeScreenshot("campus-before.png");
        }
        const auto& current = getCurrentPosition();
        x.record(current.x);
        y.record(current.y);
    }
};

Define_Module(RecordedMobility);
