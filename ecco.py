#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ecco.py - Execute PowerShell commands with log capture and real-time viewer

Compatible with: Python 3.9.13+
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import time
import re

def extract_command_name(command):
    """
    Extract a short, readable name from a command for log filename generation.
    
    Examples:
        "../bar/foo.ps1 -option1 param1" -> "foo"
        "npm install --save" -> "npm"
        "Get-Process | Where CPU -gt 100" -> "Get-Process"
        ".\\script.ps1" -> "script"
    
    Args:
        command: The full command string
        
    Returns:
        A sanitized short name suitable for filenames
    """
    # Remove leading/trailing whitespace
    command = command.strip()
    
    # Extract the first token (before first space, pipe, semicolon, etc.)
    # Split on common separators
    first_token = re.split(r'[\s|;]', command, maxsplit=1)[0]
    
    # Get just the filename (remove path)
    command_name = Path(first_token).name
    
    # Remove extension if present
    command_name = Path(command_name).stem if '.' in command_name else command_name
    
    # Sanitize for filesystem (keep only alphanumeric, dash, underscore)
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', command_name)
    
    # Limit length and clean up
    safe_name = safe_name[:30].strip('_')
    
    # Fallback if we ended up with nothing
    if not safe_name:
        safe_name = "command"
    
    return safe_name

def run_command_with_viewer(command, log_folder=None, log_file=None):
    """
    Execute a PowerShell command and capture its output with a real-time log viewer.
    
    Args:
        command: The PowerShell command to execute (plain text)
        log_folder: Folder where the log file will be created (auto-generated name)
        log_file: Specific log file path (takes precedence over log_folder)
    """
    # Generate timestamp (used in log header and optionally in filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if log_file:
        # Use the specified file path directly
        log_file_path = Path(log_file).resolve()
        # Create parent directory if needed
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Auto-generate log filename in specified or current directory
        log_path = Path(log_folder if log_folder else ".").resolve()
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Extract a short name from the command (first word/script name only)
        command_name = extract_command_name(command)
        
        # Generate log filename
        log_filename = f"log_{command_name}_{timestamp}.log"
        log_file_path = log_path.joinpath(log_filename).resolve()
    
    print(f"Executing command: {command}")
    print(f"Log file: {log_file_path}")
    
    # Count existing lines if file exists (so viewer can skip them)
    initial_line_count = 0
    if log_file_path.exists():
        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                initial_line_count = sum(1 for _ in f)
            print(f"Appending to existing log ({initial_line_count} existing lines)")
        except Exception as e:
            print(f"Warning: Could not count existing lines: {e}")
    
    # Create/append to the log file with header
    with open(log_file_path, 'a', encoding='utf-8') as log_file:
        log_file.write(f"=== Executing PowerShell Command ===\n")
        log_file.write(f"Command: {command}\n")
        log_file.write(f"Log: {log_file_path}\n")
        log_file.write(f"Started: {timestamp}\n")
        log_file.write("=" * 50 + "\n\n")
    
    # Launch log viewer console FIRST
    # Escape double quotes for PowerShell string (double them)
    command_escaped = command.replace('"', '""').replace('`', '``').replace('$', '`$')
    log_path_escaped = str(log_file_path).replace('"', '""')
    
    ps_viewer_command = f"""
    $Host.UI.RawUI.WindowTitle = "ECCO Log Viewer"
    Write-Host "=== ECCO LOG VIEWER ===" -ForegroundColor Cyan
    Write-Host "Command: {command_escaped}" -ForegroundColor Yellow
    Write-Host "Log: {log_path_escaped}" -ForegroundColor Gray
    Write-Host "==================================================="
    Write-Host ""
    
    # Follow the log file, skipping existing lines, until we see the completion marker
    Get-Content -Path '{log_path_escaped}' -Wait -Encoding UTF8 | Select-Object -Skip {initial_line_count} | ForEach-Object {{
        Write-Output $_
        if ($_ -match '\\[SUCCESS\\]|\\[ERROR\\]') {{
            # Command completed, notify user and close automatically
            Write-Host ""
            Write-Host ("===================================================") -ForegroundColor Cyan
            Write-Host "Command execution completed." -ForegroundColor Green
            Write-Host "This window will close automatically in 5 seconds..." -ForegroundColor Yellow
            Write-Host ("===================================================") -ForegroundColor Cyan
            
            # Countdown
            for ($i = 5; $i -gt 0; $i--) {{
                Write-Host "Closing in $i..." -NoNewline
                Start-Sleep -Seconds 1
                Write-Host "`r" -NoNewline
            }}
            
            # Exit the viewer
            break
        }}
    }}
    """
    
    viewer_process = subprocess.Popen([
        'conhost',
        'powershell.exe',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command', ps_viewer_command
    ], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    # Give the viewer a moment to start
    time.sleep(0.5)
    
    print(f"Log viewer console opened. Starting command execution...")
    
    # Execute the command directly without encoding tricks
    # This preserves Write-Host output properly, but may have issues with quotes/special chars
    command_process = subprocess.Popen([
        'powershell.exe',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command', command
    ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1
    )
    
    # Write output to log file in real-time
    with open(log_file_path, 'a', encoding='utf-8') as log_file:
        for line in iter(command_process.stdout.readline, ''):
            if line:
                log_file.write(line)
                log_file.flush()  # Important: flush so viewer can see it
    
    # Wait for command to complete
    command_process.wait()
    
    # Write footer to log
    end_time = datetime.now()
    with open(log_file_path, 'a', encoding='utf-8') as log_file:
        log_file.write(f"\n\n")
        log_file.write("=" * 50 + "\n")
        log_file.write(f"=== Execution completed ===\n")
        log_file.write(f"Ended: {end_time.strftime('%Y%m%d_%H%M%S')}\n")
        log_file.write(f"Exit code: {command_process.returncode}\n")
        log_file.write("=" * 50 + "\n")
        
        if command_process.returncode == 0:
            log_file.write("\n[SUCCESS] Command completed successfully.\n")
        else:
            log_file.write(f"\n[ERROR] Command failed with exit code {command_process.returncode}.\n")
    
    print(f"Completed with exit code: {command_process.returncode}")
    
    # Don't wait for the viewer to close - it will close itself after countdown
    # This allows the caller to get control back immediately
    
    # Return the exit code
    return command_process.returncode

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ecco.py <command> [log_path]")
        print("  command   : PowerShell command to execute")
        print("  log_path  : Optional log file or folder")
        print("              - If path has an extension → treated as log file")
        print("              - Otherwise → treated as log folder (auto-generates filename)")
        sys.exit(1)
    
    command = sys.argv[1]
    
    # Determine if there's a log path argument
    log_folder = None
    log_file = None
    
    if len(sys.argv) > 2:
        log_path = sys.argv[2]
        # Check if it looks like a file (has an extension)
        if '.' in Path(log_path).name:
            # Treat as specific log file
            log_file = log_path
        else:
            # Treat as log folder
            log_folder = log_path
    
    exit_code = run_command_with_viewer(command, log_folder=log_folder, log_file=log_file)
    sys.exit(exit_code)
