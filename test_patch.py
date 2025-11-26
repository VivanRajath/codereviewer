
import os
import tempfile
import subprocess

original_text = "def hello():\n    print('Hello')\n"
patch_text = "@@ -1,2 +1,2 @@\n def hello():\n-    print('Hello')\n+    print('World')\n"

def test_patch():
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Temp dir: {temp_dir}")
            
            # 1. Write original
            src_path = os.path.join(temp_dir, "temp_file")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(original_text)
                
            # 2. Create patch
            patch_header = f"--- a/temp_file\n+++ b/temp_file\n"
            full_patch = patch_header + patch_text
            
            patch_path = os.path.join(temp_dir, "patch.diff")
            with open(patch_path, "w", encoding="utf-8") as f:
                f.write(full_patch)
                
            print(f"Patch content:\n{full_patch}")

            # 3. Apply
            cmd = ["git", "apply", "--ignore-space-change", "--ignore-whitespace", "patch.diff"]
            result = subprocess.run(cmd, cwd=temp_dir, capture_output=True, text=True)
            
            print(f"Return code: {result.returncode}")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")
            
            if result.returncode == 0:
                with open(src_path, "r", encoding="utf-8") as f:
                    print(f"Resulting file:\n{f.read()}")
            else:
                print("Failed to apply patch")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_patch()
