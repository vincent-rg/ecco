# ecco.ps1 - PowerShell wrapper for executing commands with log capture
#
# Usage:
#   Direct execution: .\ecco.ps1 { command } [-LogDir <path> | -LogFile <path>]
#                     .\ecco.ps1 "command" [-LogDir <path> | -LogFile <path>]
#
#   Source and use:   . .\ecco.ps1
#                     ecco { command } [-LogDir <path> | -LogFile <path>]
#                     ecco "command" [-LogDir <path> | -LogFile <path>]
#
# Options:
#   -LogDir   : Directory for auto-generated log files (default: current directory)
#   -LogFile  : Specific log file path (takes precedence over -LogDir)

# Capture the script directory at load time (before function is called)
$script:EccoScriptDir = if ($PSScriptRoot) { 
    $PSScriptRoot 
} elseif ($MyInvocation.MyCommand.Path) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    Get-Location
}

function ecco {
    <#
    .SYNOPSIS
        Execute a PowerShell command with real-time log capture and viewer.
    
    .DESCRIPTION
        Executes a PowerShell command and captures its output to a log file.
        A separate console window displays the log in real-time and closes automatically
        when the command completes.
    
    .PARAMETER Command
        The PowerShell command to execute. Can be a ScriptBlock or a String.
    
    .PARAMETER LogDir
        Optional directory where log files will be saved with auto-generated names.
        The directory will be created if it doesn't exist.
        Mutually exclusive with -LogFile.
    
    .PARAMETER LogFile
        Optional specific log file path. Can be absolute or relative.
        The parent directory will be created if it doesn't exist.
        Mutually exclusive with -LogDir.
    
    .EXAMPLE
        ecco { Get-ChildItem -Recurse }
        
    .EXAMPLE
        ecco "Get-Process | Where-Object CPU -gt 100"
        
    .EXAMPLE
        ecco { npm install } -LogDir "./logs"
    
    .EXAMPLE
        ecco { npm install } -LogFile "./logs/install.log"
    
    .EXAMPLE
        ecco "git status" -LogFile "git-status.txt"
    #>
    
    [CmdletBinding(DefaultParameterSetName='AutoGenerate')]
    param(
        [Parameter(Mandatory=$true, Position=0)]
        [ValidateNotNull()]
        $Command,
        
        [Parameter(Mandatory=$false, ParameterSetName='UseDir')]
        [string]$LogDir,
        
        [Parameter(Mandatory=$false, ParameterSetName='UseFile')]
        [string]$LogFile
    )
    
    # Convert command to string based on its type
    $commandString = ""
    if ($Command -is [ScriptBlock]) {
        $commandString = $Command.ToString()
    }
    elseif ($Command -is [string]) {
        $commandString = $Command
    }
    else {
        $commandString = $Command.ToString()
    }
    
    # Trim whitespace
    $commandString = $commandString.Trim()

    if ([string]::IsNullOrWhiteSpace($commandString)) {
        Write-Error "Error: Command cannot be empty"
        return 1
    }

    # Escape for passing through to Python/subprocess:
    # 1. Double any backslashes before quotes (so \" becomes \\")
    # 2. Then escape the quotes themselves
    $escapedCommand = $commandString -replace '(\\*)"', '$1$1\"'
    
    # Check if Python is available
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        # Try 'py' launcher
        $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
        if (-not $pythonCmd) {
            Write-Error "Error: Python is not found in PATH. Please install Python or add it to PATH."
            return 1
        }
        $pythonExe = "py"
    }
    else {
        $pythonExe = "python"
    }
    
    # Find ecco.py script
    # Use the script directory captured at load time
    $eccoPyPath = Join-Path $script:EccoScriptDir "ecco.py"
    
    if (-not (Test-Path $eccoPyPath)) {
        # Try to find it in PATH
        $eccoPyCmd = Get-Command ecco.py -ErrorAction SilentlyContinue
        if ($eccoPyCmd) {
            $eccoPyPath = $eccoPyCmd.Source
        }
        else {
            Write-Error "Error: ecco.py not found. Please ensure ecco.py is in the same directory as ecco.ps1 or in your PATH."
            return 1
        }
    }
    
    # Execute the Python script (non-blocking - it will launch its own viewer)
    Write-Host "ECCO: Launching command execution with log viewer..." -ForegroundColor Cyan
    
    # Determine which log parameter to pass to Python
    $logPath = if ($LogFile) {
        $LogFile
    } elseif ($LogDir) {
        $LogDir
    } else {
        # Default: current directory with auto-generated name
        "."
    }
    
    # Call Python script with command and log path
    & $pythonExe $eccoPyPath $escapedCommand $logPath
    
    # Note: $LASTEXITCODE is automatically available to the caller
    # We don't return it explicitly to avoid displaying it in the console
}

# If this script is executed directly (not sourced), run the function with provided arguments
if ($MyInvocation.InvocationName -ne '.') {
    # Script was executed, not sourced
    if ($args.Count -gt 0) {
        ecco @args
        exit $LASTEXITCODE
    }
    else {
        Write-Host "ECCO wrapper loaded." -ForegroundColor Green
        Write-Host "Usage: .\ecco.ps1 { command } [-LogDir <path> | -LogFile <path>]" -ForegroundColor Yellow
        Write-Host "   or: .\ecco.ps1 `"command`" [-LogDir <path> | -LogFile <path>]" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Options:" -ForegroundColor Cyan
        Write-Host "  -LogDir   : Directory for auto-generated log files" -ForegroundColor Gray
        Write-Host "  -LogFile  : Specific log file path" -ForegroundColor Gray
        Write-Host ""
        Write-Host "To use as a function, source this script:" -ForegroundColor Cyan
        Write-Host "   . .\ecco.ps1" -ForegroundColor White
        Write-Host "Then call: ecco { command } [-LogFile <path>]" -ForegroundColor White
    }
}
# When sourced: load silently (no output to avoid polluting sub-shells)
