import os
import subprocess
from flask import Flask, render_template, request, send_from_directory
import re 
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
import time # <-- THÊM THƯ VIỆN TIME

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

FFMPEG_LOCATION = "C:\\Program Files\\ffmpeg" 
MAX_RETRIES = 10

def clean_youtube_url_robust(url: str) -> str:
    """
    Rút gọn URL YouTube chỉ giữ lại video ID, xử lý cả dạng /watch?v= và youtu.be/.
    """
    parsed_url = urlparse(url)

    # --- 1. Xử lý dạng rút gọn (youtu.be/VIDEO_ID?query) ---
    if parsed_url.netloc in ('youtu.be'):
        # Chúng ta chỉ cần Scheme, Netloc và Path. Bỏ qua Query (?si=...)
        cleaned_url = urlunparse((
            parsed_url.scheme,       # https
            parsed_url.netloc,       # youtu.be
            parsed_url.path,         # /yrlFv0-hkWE
            '',                      # params (luôn bỏ trống)
            '',                      # query (loại bỏ ?si=...)
            ''                       # fragment (loại bỏ #...)
        ))
        return cleaned_url

    # --- 2. Xử lý dạng đầy đủ (www.youtube.com/watch?v=...) ---
    elif parsed_url.netloc in ('www.youtube.com', 'youtube.com'):
        query_params = parse_qs(parsed_url.query)
        video_id_list = query_params.get('v')
        
        # Nếu không tìm thấy ID video, trả về URL gốc
        if not video_id_list:
            return url
            
        video_id = video_id_list[0]
        
        # Tạo lại query string chỉ với tham số 'v'
        new_query = urlencode({'v': video_id})
        
        cleaned_url = urlunparse((
            parsed_url.scheme,       # https
            parsed_url.netloc,       # www.youtube.com
            parsed_url.path,         # /watch
            '',                      # params
            new_query,               # v=yrlFv0-hkWE
            ''                       # fragment
        ))
        return cleaned_url
        
    # --- 3. Trường hợp URL không phải YouTube ---
    return url

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
        input_url = request.form.get('url')
        youtube_url = clean_youtube_url_robust(input_url)
        print(f"đang thấy thông tin từ {youtube_url}")
        if not youtube_url:
            error_message = "Vui lòng nhập URL YouTube."
            return render_template('index.html', download_link=download_link, error_message=error_message)

        video_id = get_youtube_id(youtube_url)
        if not video_id:
             error_message = "URL YouTube không hợp lệ."
             return render_template('index.html', error_message=error_message)
             
        output_template_raw = os.path.join(app.config['DOWNLOAD_FOLDER'], f"%(title)s-{video_id}.%(ext)s") 
        
        # --- KIỂM TRA TỒN TẠI FILE (BẰNG CÁCH TÌM KIẾM VÀ ĐỔI TÊN NẾU CẦN) ---
        found_files_with_id = [f for f in os.listdir(DOWNLOAD_FOLDER) if  video_id in f]
        
        
        if found_files_with_id:
            download_link = f"/download/{found_files_with_id[0]}"
            
            error_message = "File đã tồn tại. Đây là liên kết tải xuống."
                 
            return render_template('index.html', download_link=download_link, error_message=error_message)


        # --- BẮT ĐẦU QUÁ TRÌNH TẢI (SỬ DỤNG --cookies-from-browser) ---
        for attempt in range(MAX_RETRIES):

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
                
                break
            except subprocess.CalledProcessError as e:
                error_output = e.stderr.decode('utf-8', errors='ignore')
                if "HTTP Error 403: Forbidden" in error_output:
                    if attempt < MAX_RETRIES - 1:
                        print(f"LỖI 403: Bị từ chối truy cập. Thử lại sau 2 giây... (Lần {attempt + 1})")
                        time.sleep(2)
                        continue # Tiếp tục vòng lặp retry
                    else:
                        # Thử lại lần cuối thất bại
                        error_message = "LỖI TẢI XUỐNG: YouTube từ chối truy cập (403 Forbidden) sau nhiều lần thử. Vui lòng kiểm tra lại cookie."
                        return render_template('index.html', error_message=error_message)
                else:
                    # Lỗi khác 403, thoát và báo lỗi ngay
                    error_message = f"Lỗi Tải Xuống: {error_output}"
                    return render_template('index.html', error_message=error_message)

            except Exception as e:
                error_message = f"LỖI HỆ THỐNG: Lỗi chi tiết: {e}"
                return render_template('index.html', error_message=error_message)
        # --- KẾT THÚC VÒNG LẶP THỬ LẠI ---

        found_files_with_id = [f for f in os.listdir(DOWNLOAD_FOLDER) if  video_id in f]

        if found_files_with_id:
            download_link = f"/download/{found_files_with_id[0]}"
        else:
            error_message = "Lỗi tải file"          
        return render_template('index.html', download_link=download_link, error_message=error_message)
    return render_template('index.html', download_link=download_link, error_message=error_message)
        

# Route để phục vụ file đã tải (giữ nguyên)
@app.route('/download/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=47984, debug=True)