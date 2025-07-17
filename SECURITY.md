# Threat Model & Risk Assessment

## Security Threat Model

| STRIDE Category       | Threat                                                | Risk (H/M/L) | Mitigation                                                                                          |
|-----------------------|-------------------------------------------------------|-------------:|----------------------------------------------------------------------------------------------------|
| **S**poofing          | An attacker forges a client IP to bypass NSG rules    |         High | Enforce mTLS on API endpoints; lock down SSH to known public keys only.                            |
| **T**ampering         | Someone tampers with stored survey data               |        Medium| Use DB user permissions (least privilege); enable encryption-at-rest and integrity checks.         |
| **R**epudiation       | Lack of logs makes it hard to prove who did what      |        Medium| Centralize and forward logs (e.g. Azure Monitor or ELK); sign key events.                          |
| **I**nformation Disclosure | Metrics endpoint open to the world             |         High | Bind Prometheus and Node Exporter to localhost; reverse-proxy behind authenticated Grafana.        |
| **D**enial of Service | Flooding the app’s `/submit` endpoint                  |        Medium| Rate-limit requests; configure Azure DDoS protection; add an API gateway with throttling.         |
| **E**levation of Privilege | Malicious container escapes to host VM          |         High | Run Docker containers as unprivileged users; enable Docker seccomp and AppArmor profiles.         |

Risk Assessment:
We’ve identified three “High” risks—spoofing, info disclosure, and privilege escalation.
Our mitigations (mTLS, localhost binding, container hardening) reduce their likelihood/impact to acceptable levels.
