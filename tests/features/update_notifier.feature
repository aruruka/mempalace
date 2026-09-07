Feature: Upstream Version Update Notifier
  As an agent or developer working in a downstream workspace
  I want MemPalace to notify me when an upstream update is available
  So that I can prompt the user to upgrade without disrupting operations

  Scenario: Cache hit with a newer version displays notice without network call
    Given a workspace with cached version "0.3.0" checked 1 hour ago
    When I run a mempalace CLI command
    Then stderr displays an update banner suggesting "v0.3.0"
    And stdout remains clean and uncorrupted

  Scenario: Expired cache performs network check and caches latest release
    Given a workspace with no cache or an expired cache
    And upstream GitHub reports latest release "0.3.0"
    When I run a mempalace CLI command
    Then "MemPalace/.cache.json" is updated with "0.3.0"
    And stderr displays an update banner suggesting "v0.3.0"

  Scenario: Network failure or timeout fails silently
    Given a workspace with an expired cache
    And upstream GitHub is unreachable or times out
    When I run a mempalace CLI command
    Then the command succeeds with exit code 0
    And no error or trace is shown to the user
    And the check backs off without blocking the operation

  Scenario: Update check is disabled via environment variable
    Given the environment variable "MEMPALACE_NO_UPDATE_CHECK" is set to "1"
    When I run a mempalace CLI command
    Then no update check or banner is emitted to stderr
