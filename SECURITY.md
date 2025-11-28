# Security Policy

## Supported Versions

The following versions of CNotebook are currently supported with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of CNotebook seriously. If you discover a security vulnerability, please follow these steps:

### 1. Do Not Open a Public Issue

**Please do not report security vulnerabilities through public GitHub issues.**

This gives us time to address the vulnerability before it becomes public knowledge.

### 2. Send a Private Report

Email security reports to: **scott.arne.johnson@gmail.com**

Include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability
- Any possible mitigations you've identified

### 3. Response Timeline

- **Initial Response**: Within 48 hours of report
- **Acknowledgment**: Confirmation of issue within 5 business days
- **Updates**: Progress updates every 7 days
- **Fix Timeline**: Target resolution within 30 days for critical issues

### 4. Disclosure Policy

- **Coordinated Disclosure**: We follow coordinated vulnerability disclosure
- **Public Announcement**: After a fix is released, we'll publish a security advisory
- **Credit**: We'll credit reporters in the advisory (unless you prefer to remain anonymous)

## Security Update Process

When a security issue is confirmed:

1. We develop a fix in a private repository
2. We prepare a security advisory
3. We coordinate the release timing
4. We publish the fix and advisory simultaneously
5. We update this SECURITY.md file

## Security Best Practices for Users

### Dependency Management

CNotebook depends on:
- `pandas` - Keep updated to latest stable version
- `oepandas` - OpenEye's pandas integration
- `openeye-toolkits` - Requires commercial license

**Recommendations**:
- Keep dependencies updated to receive security patches
- Use virtual environments to isolate dependencies
- Review security advisories for dependencies regularly

### Safe Usage

- **Input Validation**: When rendering user-provided chemical structures, validate input appropriately
- **Resource Limits**: Be aware that rendering large or complex molecules can consume significant resources
- **File Operations**: Exercise caution when loading molecule files from untrusted sources

### OpenEye Toolkits

CNotebook relies on the OpenEye Toolkits, which require a commercial license. Security updates for OpenEye Toolkits are managed by OpenEye Scientific Software. Ensure your OpenEye installation is kept up to date.

## Known Security Considerations

### HTML Rendering

CNotebook generates HTML output containing embedded images. The package includes HTML escaping for text content to prevent XSS vulnerabilities. However:

- Always sanitize user input before passing to CNotebook
- Be cautious when embedding CNotebook output in web applications
- Review the generated HTML if security is a critical concern

### Resource Consumption

Rendering complex molecules or large datasets can consume significant CPU and memory:

- Set appropriate timeout limits in production environments
- Monitor resource usage when processing untrusted input
- Consider implementing rate limiting for web-based applications

## Scope

This security policy applies to:
- The CNotebook package (cnotebook)
- Official demo notebooks and examples
- Documentation

This policy does NOT cover:
- Dependencies (pandas, OpenEye Toolkits, etc.) - report to their respective maintainers
- User applications that use CNotebook
- Third-party extensions or modifications

## Contact

For security-related questions or concerns:
- **Email**: scott.arne.johnson@gmail.com
- **Subject**: Include "[SECURITY]" in the subject line

For general questions, please use GitHub Issues or Discussions instead.

## Attribution

We appreciate security researchers who responsibly disclose vulnerabilities. Contributors who report valid security issues will be acknowledged in our security advisories (with permission).

---

Thank you for helping keep CNotebook and its users safe!
