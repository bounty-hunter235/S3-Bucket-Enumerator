import subprocess
import os
import random
import string
import tempfile
import datetime

# ANSI escape codes for terminal colors
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_RESET = "\033[0m"

# Candidate AWS regions for auto-detection
CANDIDATE_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2", "af-south-1",
    "ap-east-1", "ap-south-1", "ap-south-2", "ap-northeast-1", "ap-northeast-2",
    "ap-northeast-3", "ap-southeast-1", "ap-southeast-2", "ap-southeast-3",
    "ap-southeast-4", "ap-southeast-5", "ap-southeast-7", "ca-central-1",
    "ca-west-1", "eu-central-1", "eu-central-2", "eu-west-1", "eu-west-2",
    "eu-west-3", "eu-south-1", "eu-north-1", "il-central-1", "me-south-1",
    "mx-central-1", "sa-east-1"
]

def run_command(command):
    """Run a shell command and return stdout and stderr."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return "", str(e)

def auto_detect_region(bucket_name):
    """Auto-detect bucket region by iterating candidate regions."""
    for region in CANDIDATE_REGIONS:
        cmd = f"aws s3 ls s3://{bucket_name}/ --region {region} --no-sign-request"
        stdout, stderr = run_command(cmd)
        if "An error occurred" not in stderr and stdout:
            print(f"Detected Region: {region}")
            return region
    return None

def list_s3_objects(bucket_name, region):
    """List S3 objects in the bucket using aws cli."""
    cmd = f"aws s3 ls s3://{bucket_name}/ --recursive --region {region} --no-sign-request"
    stdout, stderr = run_command(cmd)
    if stderr:
        print(f"Error listing objects: {stderr}")
        return []
    lines = [line for line in stdout.splitlines() if line.strip()]
    objects = []
    for line in lines:
        # Expected format: 2025-03-27 15:48:38       12345 path/to/object.ext
        parts = line.split()
        if len(parts) >= 4:
            objects.append({
                "date": parts[0],
                "time": parts[1],
                "size": int(parts[2]),
                "key": parts[3]
            })
    return objects

def check_read_access(bucket_name, folder, region):
    """Check if the folder has read access."""
    cmd = f"aws s3 ls s3://{bucket_name}/{folder} --region {region} --no-sign-request"
    stdout, stderr = run_command(cmd)
    if "AccessDenied" in stderr or "An error occurred" in stderr:
        return False
    return True

def check_write_access(bucket_name, folder, region):
    """Check if the folder has write access by attempting an upload."""
    test_file = ''.join(random.choices(string.ascii_letters + string.digits, k=8)) + ".txt"
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Test file for S3 write access check.")
        local_test_file = temp_file.name

    upload_cmd = f"aws s3 cp {local_test_file} s3://{bucket_name}/{folder}{test_file} --region {region} --no-sign-request"
    stdout, stderr = run_command(upload_cmd)
    os.remove(local_test_file)
    if "AccessDenied" in stderr or "An error occurred" in stderr:
        return False
    # Clean up test file from S3
    delete_cmd = f"aws s3 rm s3://{bucket_name}/{folder}{test_file} --region {region} --no-sign-request"
    run_command(delete_cmd)
    return True

def group_objects_by_folder(objects):
    """Group S3 objects by their top-level folder."""
    groups = {}
    for obj in objects:
        folder = obj["key"].split('/')[0]
        groups.setdefault(folder, []).append(obj)
    return groups

def format_size(size):
    """Format size into KB, MB, GB, or TB."""
    if size >= 1 << 40:
        return f"{size/(1<<40):.2f} TB"
    elif size >= 1 << 30:
        return f"{size/(1<<30):.2f} GB"
    elif size >= 1 << 20:
        return f"{size/(1<<20):.2f} MB"
    elif size >= 1 << 10:
        return f"{size/(1<<10):.2f} KB"
    else:
        return f"{size} bytes"

def print_folder_permissions(folder_permissions):
    """Print folder permissions in a tabular format to the command line."""
    print("\nPermissions on bucket")
    print("---------------------")
    print(f"{'Folder':<40} {'Permission':<15}")
    print("-" * 60)
    for folder in sorted(folder_permissions.keys()):
        perm = folder_permissions[folder]
        # If write access is available, mark as Read/Write; else just Read.
        permission_str = "Read/Write" if perm["write"] else "Read"
        color = COLOR_RED if perm["write"] else COLOR_GREEN
        print(f"{folder:<40} {color}{permission_str:<15}{COLOR_RESET}")

def print_grouped_files(groups):
    """Print available bucket files grouped by folder with color-coded sizes."""
    print("\nAvailable Bucket files")
    print("-------------------------------")
    for folder in sorted(groups.keys()):
        print(f"\n{COLOR_YELLOW}{folder}{COLOR_RESET}")
        print(f"{'-'*35}")
        sorted_files = sorted(groups[folder], key=lambda x: x["size"], reverse=True)
        for file in sorted_files:
            size = file["size"]
            if size == 0:
                col = COLOR_BLUE
            elif size > 100 * (1<<20):  # >100MB
                col = COLOR_RED
            elif size > 10 * (1<<20):   # >10MB
                col = COLOR_YELLOW
            else:
                col = COLOR_GREEN
            print(f"    {col}{format_size(size):>12} - {file['key']}{COLOR_RESET}")

def generate_html_report(bucket_name, region, timestamp, total_files, total_size, folder_permissions, groups):
    """Generate an HTML report with all the bucket enumeration details."""
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>S3 Bucket Report for {bucket_name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f8f9fa;
        }}
        h1, h2 {{
            color: #343a40;
        }}
        .metadata, .permissions, .files {{
            margin-bottom: 30px;
            padding: 15px;
            background-color: #fff;
            border: 1px solid #dee2e6;
            border-radius: 5px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        th, td {{
            border: 1px solid #dee2e6;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #e9ecef;
        }}
        .yes {{
            color: green;
            font-weight: bold;
        }}
        .no {{
            color: red;
            font-weight: bold;
        }}
        .folder-title {{
            background-color: #343a40;
            color: #fff;
            padding: 5px;
            border-radius: 3px;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <h1>S3 Bucket Enumeration Report</h1>
    <div class="metadata">
        <h2>Bucket Metadata</h2>
        <p><strong>Bucket Name:</strong> {bucket_name}</p>
        <p><strong>Region:</strong> {region}</p>
        <p><strong>Timestamp:</strong> {timestamp}</p>
        <p><strong>Total Files:</strong> {total_files}</p>
        <p><strong>Total Size:</strong> {format_size(total_size)}</p>
    </div>
    <div class="permissions">
        <h2>Folder Permissions</h2>
        <table>
            <tr>
                <th>Sr. No.</th>
                <th>Folder/Subfolder</th>
                <th>Permission</th>
            </tr>
    """
    for i, folder in enumerate(sorted(folder_permissions.keys()), start=1):
        perm = folder_permissions[folder]
        permission_str = "Read/Write" if perm["write"] else "Read"
        color = "red" if perm["write"] else "green"
        html_content += f"""
            <tr>
                <td>{i}</td>
                <td>{folder}</td>
                <td style="color:{color};">{permission_str}</td>
            </tr>
        """
    html_content += """
        </table>
    </div>
    <div class="files">
        <h2>Bucket Files by Folder</h2>
    """
    for folder in sorted(groups.keys()):
        html_content += f"""
        <div class="folder-section">
            <div class="folder-title">{folder}</div>
            <table>
                <tr>
                    <th>File</th>
                    <th>Size</th>
                </tr>
        """
        sorted_files = sorted(groups[folder], key=lambda x: x["size"], reverse=True)
        for file in sorted_files:
            html_content += f"""
                <tr>
                    <td>{file['key']}</td>
                    <td>{format_size(file['size'])}</td>
                </tr>
            """
        html_content += """
            </table>
        </div>
        """
    html_content += """
    </div>
</body>
</html>
    """
    with open("s3_bucket_report.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("HTML report saved as s3_bucket_report.html")

def main():
    # Prompt for bucket name
    bucket_name = input("Enter the S3 bucket name: ").strip()
    
    # Prompt for region; auto-detect if blank
    region = input("Enter the AWS region (or leave blank to auto-detect): ").strip()
    if not region:
        print("Auto-detecting region...")
        region = auto_detect_region(bucket_name)
        if not region:
            print("Failed to detect region. Exiting.")
            return
    
    # Print a single timestamp
    now = datetime.datetime.now(datetime.timezone.utc).astimezone()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"\nTimestamp: {timestamp}")
    
    # List S3 objects
    objects = list_s3_objects(bucket_name, region)
    if not objects:
        print("No objects found in bucket.")
        return

    # Group objects by top-level folder
    groups = group_objects_by_folder(objects)
    
    # Check folder permissions (only on top-level folders)
    folder_permissions = {}
    for folder in groups.keys():
        folder_path = folder + "/"  # Ensure trailing slash
        read_access = check_read_access(bucket_name, folder_path, region)
        write_access = check_write_access(bucket_name, folder_path, region)
        folder_permissions[folder] = {"read": read_access, "write": write_access}
    
    # Print folder permissions to command line
    print_folder_permissions(folder_permissions)
    
    # Print total files and total size
    total_size = sum(obj["size"] for obj in objects)
    total_files = len(objects)
    print(f"\nTotal Files: {total_files}")
    print(f"Total Size: {format_size(total_size)}")
    
    # Print available bucket files grouped by folder
    print_grouped_files(groups)
    
    # Generate HTML report containing all the details
    generate_html_report(bucket_name, region, timestamp, total_files, total_size, folder_permissions, groups)

if __name__ == "__main__":
    main()
