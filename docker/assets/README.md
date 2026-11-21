# Frozen campus inputs

`road.net.xml` is the exact passenger-road network used in the verified campus run. It was produced using SUMO netconvert 1.22.0 and the NITK bounding box and conversion flags in the campus runbook. Map data © OpenStreetMap contributors. The bundled derived road database is available under the Open Database License 1.0. [OpenStreetMap copyright and data license](https://www.openstreetmap.org/copyright) · [Map reproduction](../../docs/SUMO_NR.md#build-the-road-file)

`trustgraph-campus.pt` is the frozen CPU model state dict from the documented campus training procedure. `SHA256SUMS` identifies both inputs and is checked during the image build. [Campus model training](../../docs/CAMPUS_MODEL.md)
