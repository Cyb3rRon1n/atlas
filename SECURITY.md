# Security Policy

## Overview

Security is a core consideration of the Atlas project.

Atlas is designed to help users understand, document, and manage their self-hosted infrastructure. Because it interacts with infrastructure information and may eventually assist with operational tasks, security and responsible handling of data are critical.

We appreciate the security community and contributors who help identify and improve potential vulnerabilities.

---

# Supported Versions

During early development, Atlas may have limited supported versions.

Security updates will generally focus on:

| Version            | Supported      |
| ------------------ | -------------- |
| Latest release     | ✅              |
| Development branch | ✅              |
| Older releases     | ⚠️ Best effort |

As Atlas matures, this policy will be updated with a formal support lifecycle.

---

# Reporting a Security Vulnerability

Please do not publicly disclose security vulnerabilities through:

* GitHub Issues
* Discussions
* Pull Requests

before maintainers have had an opportunity to investigate and address the issue.

---

## What to Include

When reporting a security concern, please include:

* Description of the vulnerability
* Potential impact
* Steps to reproduce
* Affected component
* Relevant logs or screenshots (if safe to share)
* Suggested mitigation (if known)

Please avoid including:

* Passwords
* API keys
* Private certificates
* Personal information
* Full infrastructure exports containing sensitive data

---

# Response Process

After receiving a report, maintainers will:

1. Confirm receipt of the report
2. Investigate the issue
3. Determine severity and impact
4. Develop a fix or mitigation
5. Coordinate disclosure when appropriate
6. Publish relevant information after remediation

---

# Security Principles

Atlas follows these principles:

## Least Privilege

Components should receive only the access they require.

---

## Local-First

Whenever practical, user data should remain under the user's control.

---

## Transparency

Security-related decisions should be documented and explainable.

---

## Safe Automation

Automation should:

* Require appropriate permissions
* Provide visibility into actions
* Maintain logs
* Avoid destructive behavior without approval

---

## No Secrets in the Repository

Never commit:

* Passwords
* Tokens
* API keys
* Private keys
* Environment files containing secrets

Use examples and templates instead.

---

# AI Security Considerations

Atlas includes AI-assisted functionality, which introduces additional considerations.

AI systems should not:

* Execute dangerous actions without approval
* Expose sensitive infrastructure information
* Store secrets unnecessarily
* Make unexplained infrastructure changes

AI recommendations should remain:

* Explainable
* Reviewable
* Auditable

---

# Responsible Disclosure

Atlas contributors and users are encouraged to report security issues responsibly.

We appreciate researchers and community members who help improve the project.

---

# Future Security Improvements

Planned improvements may include:

* Security scanning in CI/CD
* Dependency monitoring
* Automated vulnerability checks
* Permission auditing
* Configuration security analysis
* Infrastructure hardening recommendations

---

# Thank You

Security is a community effort.

Every report, suggestion, and improvement helps make Atlas a safer platform for everyone building self-hosted infrastructure.
