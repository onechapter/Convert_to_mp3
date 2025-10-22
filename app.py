import os
import subprocess
from flask import Flask, render_template, request, send_from_directory
import re 
from urllib.parse import urlparse, parse_qs 
import time # <-- THÊM THƯ VIỆN TIME

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

FFMPEG_LOCATION = "C:\\Program Files\\ffmpeg" 

# --- HÀM LẤY ID YOUTUBE (Giữ nguyên) ---
def get_youtube_id(url):
    if 'v=' in url:
        query = urlparse(url).query
        return parse_qs(query).get('v', [None])[0]
    elif 'youtu.be' in url:
        return urlparse(url).path[1:]
    return None

# --- HÀM ĐỔI TÊN FILE SAU KHI TẢI (Thêm logic đổi tên) ---
def rename_and_clean_file(download_folder, old_file_name, video_id):
    """Loại bỏ ID khỏi tên file và đổi tên, cố gắng 3 lần nếu thất bại."""
    if not old_file_name.startswith(f"{video_id}-"):
        return old_file_name # Không có ID để xóa
        
    new_file_name = old_file_name.replace(f"{video_id}-", "", 1)
    
    old_path = os.path.join(download_folder, old_file_name)
    new_path = os.path.join(download_folder, new_file_name)

    # Thử đổi tên 3 lần với độ trễ
    for i in range(3):
        try:
            # Nếu tên file mới đã tồn tại, xóa file cũ đi (đề phòng)
            if os.path.exists(new_path):
                os.remove(new_path)
            
            os.rename(old_path, new_path)
            return new_file_name # Đổi tên thành công
        except Exception:
            if i < 2:
                time.sleep(3) # Chờ 0.5 giây rồi thử lại
            else:
                return old_file_name # Đổi tên thất bại sau 3 lần thử


@app.route('/', methods=['GET', 'POST'])
def index():
    download_link = None
    error_message = None

    if request.method == 'POST':
        youtube_url = request.form.get('url')
        if not youtube_url:
            error_message = "Vui lòng nhập URL YouTube."
            return render_template('index.html', download_link=download_link, error_message=error_message)

        video_id = get_youtube_id(youtube_url)
        if not video_id:
             error_message = "URL YouTube không hợp lệ."
             return render_template('index.html', error_message=error_message)
             
        output_template_raw = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{video_id}-%(title)s.%(ext)s") 
        
        # --- KIỂM TRA TỒN TẠI FILE (BẰNG CÁCH TÌM KIẾM VÀ ĐỔI TÊN NẾU CẦN) ---
        found_files_with_id = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(f"{video_id}-") and f.endswith(".mp3")]
        found_files_without_id = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith(".mp3") and not f.startswith(f"{video_id}-")] 
        
        final_existing_file = None
        
        # 1. Ưu tiên file đã đổi tên (không có ID)
        for f in found_files_without_id:
            # Kiểm tra xem file không ID có chứa ID video không (đảm bảo nó là file của video này)
            if video_id in f:
                final_existing_file = f
                break

        # 2. Nếu không có, tìm file có ID và tiến hành đổi tên
        if not final_existing_file and found_files_with_id:
            old_file_name = found_files_with_id[0]
            new_file_name = rename_and_clean_file(app.config['DOWNLOAD_FOLDER'], old_file_name, video_id)
            final_existing_file = new_file_name
        
        
        if final_existing_file:
            download_link = f"/download/{final_existing_file}"
            
            # Cảnh báo nếu đổi tên thất bại (file vẫn còn ID)
            if final_existing_file.startswith(f"{video_id}-"):
                 error_message = "Cảnh báo: File đã tồn tại nhưng không thể đổi tên (vẫn còn ID). Vui lòng kiểm tra quyền truy cập file."
            else:
                 error_message = "File đã tồn tại. Đây là liên kết tải xuống."
                 
            return render_template('index.html', download_link=download_link, error_message=error_message)


        # --- BẮT ĐẦU QUÁ TRÌNH TẢI (SỬ DỤNG --cookies-from-browser) ---
        try:
            command = [
                'yt-dlp',
                '-x',                       
                '--audio-format', 'mp3',
                '-f', 'bestaudio',
                '--cookies-from-browser', 'firefox', 
                '--ffmpeg-location', FFMPEG_LOCATION, 
                '--no-playlist',            
                '--output', output_template_raw, 
                '--sleep-requests', '1', 
                '--no-warnings', 
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', 
                '--add-header', 'Accept-Language: en-US,en;q=0.5', 
                youtube_url                 
            ]
            
            result = subprocess.run(command, check=True, capture_output=True) 
            
            # 3. PHÂN TÍCH LOG CỦA YT-DLP để lấy tên file chính xác
            old_file_name = None
            output_log = result.stdout.decode('utf-8', errors='ignore') + result.stderr.decode('utf-8', errors='ignore')
            
            match = re.search(r'Destination: {}(.+?\.mp3)'.format(re.escape(DOWNLOAD_FOLDER + os.sep)), output_log)
            
            if match:
                old_file_name = match.group(1).strip()
            
            
            if old_file_name and os.path.exists(os.path.join(app.config['DOWNLOAD_FOLDER'], old_file_name)):
                
                # --- THAO TÁC ĐỔI TÊN MỚI (Thêm độ trễ và gọi hàm đổi tên) ---
                time.sleep(1) # Rất quan trọng: Chờ ffmpeg giải phóng file
                new_file_name = rename_and_clean_file(app.config['DOWNLOAD_FOLDER'], old_file_name, video_id)
                
                if new_file_name != old_file_name:
                    download_link = f"/download/{new_file_name}"
                else:
                    download_link = f"/download/{old_file_name}"
                    error_message = "Cảnh báo: Đổi tên thất bại. Liên kết tải xuống sử dụng tên cũ (có ID)."
                # -----------------------------
                
            else:
                error_message = f"Tải xuống thành công nhưng không tìm thấy file MP3 cuối cùng."

        except subprocess.CalledProcessError as e:
            error_output = e.stderr.decode('utf-8', errors='ignore')
            if "HTTP Error 403: Forbidden" in error_output:
                 error_message = "LỖI TẢI XUỐNG: YouTube từ chối truy cập (403 Forbidden). Vui lòng đảm bảo Firefox đã đóng và bạn đã đăng nhập YouTube."
            else:
                 error_message = f"Lỗi Tải Xuống: {error_output}"
        
        except Exception as e:
            error_message = f"LỖI HỆ THỐNG: Lỗi chi tiết: {e}"
        
    return render_template('index.html', download_link=download_link, error_message=error_message)

# Route để phục vụ file đã tải (giữ nguyên)
@app.route('/download/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)