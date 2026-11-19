#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <thread>
#include <vector>

#include <omnetpp.h>
#include "simu5g/common/binder/Binder.h"
#include "simu5g/stack/ip2nic/HandoverPacketHolderUe.h"
#include "simu5g/stack/mac/LteMacUe.h"
#include "simu5g/stack/phy/feedback/LteDlFeedbackGenerator.h"
#include "simu5g/stack/rlc/um/NrRlcUmTxEntity.h"
#include "simu5g/stack/rrc/ConnectionControlUe.h"
#include "veins_inet/VeinsInetMobility.h"

using namespace omnetpp;
namespace fs = std::filesystem;

class PolicyBridge : public cSimpleModule, public cListener
{
    cMessage *sampleTimer = nullptr;
    cMessage *earlyTimer = nullptr;
    cModule *mac[2]{};
    double blocks[2]{};
    long slots[2]{};
    int tick = 1;
    long serial = 0;
    simtime_t lastEarly = SimTime(-2);
    cOutVector gnb1Backlog{"gnb1DlBacklogBytes"};
    cOutVector gnb2Backlog{"gnb2DlBacklogBytes"};

    void proposeEarly();

    static int64_t queuedBytes(cModule *module)
    {
        if (auto *rlc = dynamic_cast<simu5g::NrRlcUmTxEntity *>(module))
            return rlc->getBufferOccupancy();
        int64_t total = 0;
        for (cModule::SubmoduleIterator child(module); !child.end(); ++child)
            total += queuedBytes(*child);
        return total;
    }

protected:
    int numInitStages() const override { return inet::NUM_INIT_STAGES; }
    void initialize(int stage) override
    {
        if (stage != inet::NUM_INIT_STAGES - 1 || (!enabled() && !par("recordBacklog").boolValue()))
            return;
        for (int cell = 0; cell < 2; ++cell) {
            mac[cell] = getParentModule()->getModuleByPath(cell == 0 ? ".gnb1.cellularNic.mac" : ".gnb2.cellularNic.mac");
            if (!mac[cell])
                throw cRuntimeError("Missing gNB MAC for policy telemetry");
            mac[cell]->subscribe("avgServedBlocksDl", this);
        }
        sampleTimer = new cMessage("policyTelemetry");
        if (par("earlyOffload").boolValue())
            earlyTimer = new cMessage("policyEarlyOffload");
        scheduleAt(SimTime(100001, SIMTIME_US), sampleTimer);
    }

    void receiveSignal(cComponent *source, simsignal_t, double value, cObject *) override
    {
        registerBlocks(source, value);
    }

    void receiveSignal(cComponent *source, simsignal_t, intval_t value, cObject *) override
    {
        registerBlocks(source, value);
    }

    void registerBlocks(cComponent *source, double value)
    {
        int cell = source == mac[0] ? 0 : 1;
        blocks[cell] += value;
        ++slots[cell];
    }

    void handleMessage(cMessage *message) override
    {
        if (message == earlyTimer) {
            proposeEarly();
            return;
        }
        double load[2]{};
        for (int cell = 0; cell < 2; ++cell) {
            if (slots[cell] != 100)
                throw cRuntimeError("Expected 100 MAC slots per policy observation");
            load[cell] = blocks[cell] / (par("rbCapacity").intValue() * slots[cell]);
            blocks[cell] = 0;
            slots[cell] = 0;
        }
        auto *network = getParentModule();
        if (par("recordBacklog").boolValue()) {
            gnb1Backlog.record(queuedBytes(mac[0]->getParentModule()));
            gnb2Backlog.record(queuedBytes(mac[1]->getParentModule()));
        }
        if (enabled())
        for (int index = 0; index < network->getSubmoduleVectorSize("car"); ++index) {
            auto *car = network->getSubmodule("car", index);
            if (car == nullptr)
                continue;
            auto *mobility = check_and_cast<veins::VeinsInetMobility *>(car->getSubmodule("mobility"));
            auto *rrc = check_and_cast<simu5g::ConnectionControlUe *>(
                car->getModuleByPath(".cellularNic.rrc.nrConnectionControl"));
            const auto& position = mobility->getCurrentPosition();
            EV_INFO << "TRUSTGRAPH_OBS " << tick << " " << simu5g::num(rrc->getNodeId())
                    << " " << position.x - 25 << " " << 25 - position.y
                    << " " << mobility->getCurrentVelocity().length()
                    << " " << simu5g::num(rrc->getServingNodeId())
                    << " " << load[0] << " " << load[1] << "\n";
        }
        if (earlyTimer && tick % 10 == 0 && load[0] > 0.8 && load[1] <= 0.6 && simTime() - lastEarly >= SimTime(2))
            // Native RRC evaluates each beacon 10 us after arrival.
            scheduleAt(simTime() + SimTime(20, SIMTIME_US), earlyTimer);
        ++tick;
        scheduleAt(simTime() + SimTime(100, SIMTIME_MS), message);
    }

    void finish() override
    {
        for (auto *module : mac)
            if (module)
                module->unsubscribe("avgServedBlocksDl", this);
    }

public:
    ~PolicyBridge() override { cancelAndDelete(sampleTimer); cancelAndDelete(earlyTimer); }
    bool enabled() const { return par("enabled").boolValue(); }

    std::string ask(int ue, int current, int candidate, double *earlyRssi = nullptr)
    {
        Enter_Method_Silent();
        const long sequence = ++serial;
        const auto suffix = std::to_string(sequence);
        const fs::path temporary = "bridge/request-" + suffix + ".tmp";
        const fs::path request = "bridge/request-" + suffix + ".txt";
        const fs::path response = "bridge/response-" + suffix + ".txt";
        {
            std::ofstream stream(temporary);
            stream << sequence << " " << simTime() << " " << ue << " " << current << " " << candidate;
            if (earlyRssi)
                stream << " early";
            stream << "\n";
            if (!stream)
                return "fallback_io";
        }
        std::error_code error;
        fs::rename(temporary, request, error);
        if (error)
            return "fallback_io";
        const auto deadline = std::chrono::steady_clock::now()
            + std::chrono::milliseconds(par("responseTimeoutMs").intValue());
        while (std::chrono::steady_clock::now() < deadline) {
            std::ifstream stream(response);
            long received;
            std::string decision;
            if (stream >> received >> decision && received == sequence) {
                if (earlyRssi && decision == "request" && !(stream >> *earlyRssi))
                    return "fallback_io";
                return decision;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        return "fallback_timeout";
    }
};

Define_Module(PolicyBridge);

class PolicyConnectionControl : public simu5g::ConnectionControlUe
{
    bool policyHandover = false;
    bool deferredOnce = false;
    bool earlyAttempted = false;
    bool earlyHandover = false;

    void triggerHandover() override
    {
        auto *bridge = check_and_cast<PolicyBridge *>(getSimulation()->getSystemModule()->getSubmodule("policy"));
        if (!bridge->enabled() || servingNodeId_ == simu5g::NODEID_NONE ||
            candidateServingNodeId_ == simu5g::NODEID_NONE || servingNodeId_ == candidateServingNodeId_) {
            ConnectionControlUe::triggerHandover();
            return;
        }
        auto decision = bridge->ask(simu5g::num(nodeId_), simu5g::num(servingNodeId_),
                                    simu5g::num(candidateServingNodeId_));
        if (decision == "defer" && deferredOnce)
            decision = "fallback_deferred_once";
        EV_INFO << "TRUSTGRAPH_DECISION " << simTime() << " " << simu5g::num(nodeId_)
                << " " << simu5g::num(servingNodeId_) << " " << simu5g::num(candidateServingNodeId_)
                << " " << decision << "\n";
        if (decision == "defer") {
            deferredOnce = true;
            candidateServingNodeId_ = servingNodeId_;
            candidateServingNodeRssi_ = servingNodeRssi_;
            updateHysteresisThreshold(servingNodeRssi_);
            triggeredHandover_.reset();
            return;
        }
        policyHandover = decision == "request";
        ConnectionControlUe::triggerHandover();
        if (policyHandover && (!handoverTrigger_ || !handoverTrigger_->isScheduled())) {
            EV_INFO << "TRUSTGRAPH_REQUEST_REJECTED " << simTime() << " " << simu5g::num(nodeId_) << "\n";
            policyHandover = false;
        }
    }

    void doHandover() override
    {
        ConnectionControlUe::doHandover();
        if (policyHandover)
            EV_INFO << "TRUSTGRAPH_REQUEST_COMPLETED " << simTime() << " " << simu5g::num(nodeId_)
                    << " " << simu5g::num(servingNodeId_) << "\n";
        if (earlyHandover)
            EV_INFO << "TRUSTGRAPH_EARLY_COMPLETED " << simTime() << " " << simu5g::num(nodeId_)
                    << " " << simu5g::num(servingNodeId_) << "\n";
        policyHandover = false;
        earlyHandover = false;
        deferredOnce = false;
    }

public:
    bool hasPendingHandover() const
    {
        return (handoverStarter_ && handoverStarter_->isScheduled()) ||
               (handoverTrigger_ && handoverTrigger_->isScheduled());
    }

    bool proposeOffload(PolicyBridge *bridge)
    {
        Enter_Method_Silent();
        if (!enableHandover_ || !isNr_ || simu5g::num(servingNodeId_) != 1 || earlyAttempted || hasPendingHandover())
            return false;
        double targetRssi = 0;
        auto decision = bridge->ask(simu5g::num(nodeId_), 1, 2, &targetRssi);
        if (decision != "request") {
            EV_INFO << "TRUSTGRAPH_EARLY_SKIPPED " << simTime() << " " << simu5g::num(nodeId_)
                    << " " << decision << "\n";
            return false;
        }
        if (!std::isfinite(targetRssi) || targetRssi < std::max(40.0, minRssi_))
            return false;

        earlyAttempted = true;
        earlyHandover = policyHandover = true;
        candidateServingNodeId_ = static_cast<simu5g::MacNodeId>(2);
        candidateServingNodeRssi_ = targetRssi;
        triggeredHandover_ = std::make_pair(servingNodeId_, candidateServingNodeId_);
        EV_INFO << "TRUSTGRAPH_EARLY_REQUEST " << simTime() << " " << simu5g::num(nodeId_) << "\n";
        EV_INFO << "TRUSTGRAPH_DECISION " << simTime() << " " << simu5g::num(nodeId_) << " 1 2 request\n";
        ConnectionControlUe::triggerHandover();
        if (!handoverTrigger_ || !handoverTrigger_->isScheduled()) {
            EV_INFO << "TRUSTGRAPH_REQUEST_REJECTED " << simTime() << " " << simu5g::num(nodeId_) << "\n";
            earlyHandover = policyHandover = false;
            candidateServingNodeId_ = servingNodeId_;
            candidateServingNodeRssi_ = servingNodeRssi_;
            updateHysteresisThreshold(servingNodeRssi_);
            triggeredHandover_.reset();
        }
        return true;
    }
};

Define_Module(PolicyConnectionControl);

void PolicyBridge::proposeEarly()
{
    auto *network = getParentModule();
    std::vector<PolicyConnectionControl *> controllers;
    for (int index = 0; index < network->getSubmoduleVectorSize("car"); ++index) {
        auto *car = network->getSubmodule("car", index);
        if (!car)
            continue;
        auto *rrc = check_and_cast<PolicyConnectionControl *>(
            car->getModuleByPath(".cellularNic.rrc.nrConnectionControl"));
        if (rrc->hasPendingHandover())
            return;
        controllers.push_back(rrc);
    }
    for (auto *rrc : controllers) {
        if (rrc->proposeOffload(this)) {
            lastEarly = simTime();
            return;
        }
    }
}
