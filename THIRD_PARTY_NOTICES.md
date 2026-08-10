# Third-Party Notices And Project Origin

## AI-CPS Origin

This project is a domain-specific continuation of concepts and deployment
structures from **AI-CPS**, originally developed by Dr.-Ing. Marcus Grum:

- Repository: <https://github.com/MarcusGrum/AI-CPS>
- Upstream license: GNU Affero General Public License v3.0
- Author: Marcus Grum

Early versions of this project adapted the upstream separation of knowledge,
activation and code bases as well as its container-oriented scenario layout.
The current MQTT inference services, Node-RED simulation, training workflows
and fischertechnik-specific models were subsequently developed for this
project. The adapted work and this repository are distributed under
`AGPL-3.0-only`.

The scientific design also refers to:

> Marcus Grum (2024), "Researching Multi-Site Artificial Neural Networks'
> Activation Rates and Activation Cycles".

The complete paper is not redistributed in this runtime repository. It is
cited as a scientific source only.

## Runtime Dependencies

The project includes or uses third-party software under its respective
licenses. Important direct components include:

- Node-RED: Apache License 2.0
- FlowFuse Dashboard: Apache License 2.0
- TensorFlow/Keras: Apache License 2.0
- Eclipse Mosquitto and Paho MQTT: EPL-2.0 and/or EDL-1.0
- Python: Python Software Foundation License
- NumPy, pandas and scikit-learn: BSD-style licenses
- Docker base images and transitive packages: their respective upstream
  licenses

Lock files and container SBOM attestations identify the exact dependency
versions used by a release. Those components are not relicensed by this
repository's AGPL license.
