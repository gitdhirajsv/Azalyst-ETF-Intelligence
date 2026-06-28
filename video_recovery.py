import os
import argparse
import time

def scan_and_recover(drive_path, output_dir, file_ext, chunk_size_mb):
    """
    Scans a raw disk for video file signatures and extracts chunks of data.
    """
    signatures = {
        'mp4': [b'ftyp'],
        'avi': [b'RIFF'],
        'mov': [b'ftyp']
    }
    
    if file_ext not in signatures:
        print(f"Unsupported file extension: {file_ext}")
        return

    chunk_size = chunk_size_mb * 1024 * 1024
    read_size = 10 * 1024 * 1024  # Read 10 MB at a time to be efficient

    print(f"[*] Opening drive: {drive_path} (Requires Administrator privileges)")
    try:
        drive = open(drive_path, "rb")
    except PermissionError:
        print("[!] Permission Denied. You MUST run this script as Administrator.")
        return
    except Exception as e:
        print(f"[!] Failed to open drive: {e}")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"[*] Starting scan for {file_ext} files. This may take a long time...")
    
    recovered_count = 0
    offset = 0

    try:
        while True:
            data = drive.read(read_size)
            if not data:
                break
            
            # Simple signature search
            found_idx = -1
            if file_ext == 'mp4' or file_ext == 'mov':
                found_idx = data.find(b'ftyp')
                if found_idx != -1:
                    # 'ftyp' is usually 4 bytes after the start of the file length header
                    found_idx -= 4
            elif file_ext == 'avi':
                found_idx = data.find(b'RIFF')
                if found_idx != -1:
                    # Verify it's actually an AVI by checking the AVI signature 8 bytes later
                    if len(data) > found_idx + 12 and data[found_idx+8:found_idx+12] == b'AVI ':
                        pass
                    else:
                        found_idx = -1
            
            if found_idx != -1 and found_idx >= 0:
                absolute_pos = offset + found_idx
                print(f"[+] Found {file_ext} signature at offset: {absolute_pos}")
                
                # Seek to the start of the file
                drive.seek(absolute_pos)
                
                # Read the chunk
                print(f"    Extracting {chunk_size_mb}MB chunk...")
                file_data = drive.read(chunk_size)
                
                output_file = os.path.join(output_dir, f"recovered_video_{recovered_count}.{file_ext}")
                with open(output_file, "wb") as f_out:
                    f_out.write(file_data)
                    
                print(f"    Saved to: {output_file}")
                recovered_count += 1
                
                # Continue reading after the extracted chunk
                offset = absolute_pos + chunk_size
                drive.seek(offset)
            else:
                offset += len(data)
                
            # Print progress every ~1GB
            if offset % (1024 * 1024 * 1024) < read_size:
                print(f"[*] Scanned {offset / (1024*1024*1024):.2f} GB...")

    except KeyboardInterrupt:
        print("\n[*] Scan interrupted by user.")
    except Exception as e:
        print(f"\n[!] Error during scan: {e}")
    finally:
        drive.close()
        print(f"[*] Scan complete. Recovered {recovered_count} files.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Raw Disk Video File Carver")
    parser.add_argument("--drive", required=True, help="Drive to scan, e.g., \\\\.\\C: or \\\\.\\PhysicalDrive0")
    parser.add_argument("--output", required=True, help="Directory to save recovered files (MUST BE ON A DIFFERENT DRIVE)")
    parser.add_argument("--ext", default="mp4", choices=["mp4", "avi", "mov"], help="Video format to recover (mp4, avi, mov)")
    parser.add_argument("--size", type=int, default=100, help="Size in MB to extract per found video (default: 100MB)")
    
    args = parser.parse_args()
    scan_and_recover(args.drive, args.output, args.ext, args.size)
