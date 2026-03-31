# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [Unreleased]

### Added

- Initial single-user link dashboard implementation
- Context-based organization for links
- DNS, HTTP, and SSL checks
- Change log tracking for DNS and certificate changes
- Built-in theme system
- Context icon picker with categories and search
- Dockerfile and Docker Compose setup for single-container deployment

### Changed

- Frontend is now served directly by FastAPI on the root route

### Fixed

- Theme switching now applies correctly
- Detail panel and change log error handling improved
- Check actions now expose clearer button state feedback
