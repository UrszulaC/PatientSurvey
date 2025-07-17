# Threat Model & Risk Assessment

Below is a simple STRIDE analysis for the Patient Survey app:

| Threat                    | Description                                            | Mitigation                                                                 | Likelihood | Impact |
|---------------------------|--------------------------------------------------------|----------------------------------------------------------------------------|------------|--------|
| **S**poofing              | An attacker could impersonate a legitimate user/agent | Enforce authenticated API calls (e.g. JWT or mTLS); lock down DB creds     | Medium     | High   |
| **T**ampering             | In-flight modification of survey payloads             | Serve all endpoints over HTTPS; use parameterized SQL to prevent tampering | Medium     | High   |
| **R**epudiation           | Users deny having submitted feedback                  | Log submission events with timestamps and unique IDs                       | Low        | Medium |
| **I**nformation Disclosure| Leakage of secrets or PII                              | Don’t check in secrets; enable GitHub secret scanning; encrypt data at rest| Medium     | High   |
| **D**enial of Service     | Flooding API to make it unavailable                    | Rate-limit requests; autoscale; set up firewall rules                      | Low        | Medium |
| **E**levation of Privilege| SQL injection to gain DB admin rights                  | Use parameterized queries; validate & sanitize inputs                      | Low        | High   |
