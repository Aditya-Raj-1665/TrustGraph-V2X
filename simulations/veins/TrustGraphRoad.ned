import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.ethernet.Eth10G;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.corenetwork.bearerConfigurator.BearerConfigurator;
import simu5g.corenetwork.coreControl.CoreControl;
import simu5g.nodes.gNodeB;
import simu5g.nodes.NrCar;
import simu5g.nodes.Upf;
import simu5g.world.radio.LteChannelControl;
import simu5g.stack.rrc.ConnectionControlUe;
import org.car2x.veins.subprojects.veins_inet.VeinsInetManagerForker;
import org.car2x.veins.subprojects.veins_inet.VeinsInetMobility;

simple RecordedMobility extends VeinsInetMobility
{
    parameters:
        @class(RecordedMobility);
}

module TrustGraphCar extends NrCar
{
    parameters:
        mobility.typename = "RecordedMobility";
}

simple PolicyConnectionControl extends ConnectionControlUe
{
    parameters:
        @class(PolicyConnectionControl);
}

simple PolicyBridge
{
    parameters:
        bool enabled = default(false);
        bool earlyOffload = default(false);
        bool recordBacklog = default(false);
        int rbCapacity = default(50);
        int responseTimeoutMs = default(2000);
        @class(PolicyBridge);
}

simple SingleCarBearerConfigurator extends BearerConfigurator
{
    parameters:
        @class(SingleCarBearerConfigurator);
        int expectedCars = default(1);
}

network TrustGraphRoad
{
    parameters:
        **.cellularNic.hasSdap = default(true);
    submodules:
        configurator: Ipv4NetworkConfigurator;
        channelControl: LteChannelControl;
        binder: Binder;
        bearerConfigurator: SingleCarBearerConfigurator;
        coreControl: CoreControl;
        carrierAggregation: CarrierAggregation;
        server: StandardHost;
        router: Router;
        upf: Upf;
        iUpf: Upf;
        gnb1: gNodeB;
        gnb2: gNodeB;
        policy: PolicyBridge;
        veinsManager: VeinsInetManagerForker;
        car[0]: TrustGraphCar;
    connections:
        server.pppg++ <--> Eth10G <--> router.pppg++;
        router.pppg++ <--> Eth10G <--> upf.dnPppg;
        upf.pppg++ <--> Eth10G <--> iUpf.pppg++;
        iUpf.pppg++ <--> Eth10G <--> gnb1.ppp;
        iUpf.pppg++ <--> Eth10G <--> gnb2.ppp;
        gnb1.x2++ <--> Eth10G <--> gnb2.x2++;
}
