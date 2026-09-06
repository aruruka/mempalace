Feature: Workspace Initializer
  As a developer or coding agent
  I want to initialize a workspace for MemPalace
  So that persistent agent memory and kick-off prompts are automatically scaffolded

  Scenario: Scaffolding a fresh workspace creates required directories and database
    Given a clean target workspace directory
    When the CLI initializes the workspace for "antigravity"
    Then the workspace has a MemPalace essences directory
    And the workspace has a starter essence file
    And the workspace has a memory SQLite database
    And the workspace has an AGENTS.md file
    And the workspace has a memory-sync skill file
    And the workspace has automated setup scripts
    And the workspace has a kickoff prompt file

  Scenario: Initializing generates a tailored kickoff prompt for Claude
    Given a clean target workspace directory
    When the CLI initializes the workspace for "claude"
    Then the workspace has a CLAUDE.md file
    And the kickoff prompt references "CLAUDE.md"

  Scenario: Initializing an existing workspace is idempotent
    Given a clean target workspace directory
    When the CLI initializes the workspace for "generic"
    And the CLI initializes the workspace for "generic" again
    Then the workspace has a memory SQLite database
    And the kickoff prompt file still exists

