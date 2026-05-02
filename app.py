from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

app = Flask(__name__)
CORS(app)

# 配置区域
VOLCENGINE_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
VOLCENGINE_IMAGE_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
VOLCENGINE_API_KEY = "3f20c972-1f14-4491-8f22-44cd96d77354"

# ✅ 可用文字模型列表（火山引擎 ARK 可用模型）
TEXT_MODELS = [
    "doubao-seed-2-0-lite-260215",
    "doubao-pro-4-240615",
    "doubao-beta-241215",
    "doubao-seed-2-5-250515",
    "doubao-seed-2-0-lite-250423",
    "doubao-seed-2-0-pro-250528",
]
# ✅ 可用图片生成模型列表
IMAGE_MODELS = [
    "doubao-seedream-4-5-251128",
    "doubao-seedream-3-1-250828",
    "doubao-seedream-3-0-250515",
    "doubao-seedream-2-250313",
    "doubao-seedream-2-1-250416",
]
# 🔷 默认选中的模型
DEFAULT_TEXT_MODEL = TEXT_MODELS[0]
DEFAULT_IMAGE_MODEL = IMAGE_MODELS[0]
IMAGE_SIZE = "1920x1920"
MAX_CONCURRENT_IMAGES = 6

STYLE_ENHANCEMENTS = {
    "治愈暖色调": "warm pastel palette, cozy atmosphere, soft focus, bright and uplifting mood",
    "知识干货风": "clean minimal layout, professional editorial style, sharp focus, intellectual mood, muted earth tones",
    "简约文艺风": "Nordic minimalism, whitespace, elegant serif typography background, refined and serene atmosphere",
    "电影感构图": "cinematic composition, anamorphic lens flare, film still aesthetic, dramatic rim lighting, Moody color grading",
    "手账日记风": "hand-drawn illustration style, watercolour texture, pastel colors, scrapbook aesthetic, handwritten text elements",
    "价值成长风": "refined editorial magazine layout, confident warm tones, premium intellectual aesthetic, professional yet approachable, clean typography, slight golden accent lighting",
}

PROMPT_QUALITY_TEMPLATE = (
    "book illustration style, warm natural lighting, soft side light, "
    "shallow depth of field, film grain texture, slightly desaturated, "
    "high quality, detailed, Instagram photo style"
)

def enhance_prompt(base_prompt: str, style: str = "") -> str:
    enhanced = f"{base_prompt}, {PROMPT_QUALITY_TEMPLATE}"
    if style and style in STYLE_ENHANCEMENTS:
        enhanced = f"{base_prompt}, {STYLE_ENHANCEMENTS[style]}"
    return enhanced

def generate_single_image(prompt: str, size: str = IMAGE_SIZE, timeout: int = 120, model: str = None) -> Dict[str, Any]:
    if model is None:
        model = DEFAULT_IMAGE_MODEL
    headers = {
        "Authorization": f"Bearer {VOLCENGINE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "url"
    }
    
    print(f"DEBUG 发送图片请求: model={model}, size={size}")
    print(f"DEBUG prompt前50字: {prompt[:50]}...")
    
    try:
        response = requests.post(VOLCENGINE_IMAGE_URL, headers=headers, json=payload, timeout=timeout)
        result = response.json()
        
        print(f"DEBUG 图片API返回: status={response.status_code}")
        print(f"DEBUG 返回body: {result}")
        
        if response.status_code == 200:
            image_url = None
            
            # 尝试多种可能的数据格式
            if "data" in result and "image_urls" in result["data"]:
                urls = result["data"]["image_urls"]
                if urls and len(urls) > 0:
                    image_url = urls[0]
            elif "data" in result and "url" in result["data"]:
                image_url = result["data"]["url"]
            elif "image_url" in result:
                image_url = result["image_url"]
            elif "url" in result:
                image_url = result["url"]
            elif "data" in result and isinstance(result["data"], list):
                if result["data"]:
                    image_url = result["data"][0] if isinstance(result["data"][0], str) else result["data"][0].get("url")
            
            if image_url:
                return {"success": True, "url": image_url, "prompt": prompt}
            else:
                return {"success": False, "error": f"未找到图片URL，返回内容: {result}", "prompt": prompt}
        else:
            return {"success": False, "error": f"API错误: {response.status_code} - {result}", "prompt": prompt}
    except Exception as e:
        print(f"DEBUG 图片生成异常: {e}")
        return {"success": False, "error": str(e), "prompt": prompt}

def generate_images_parallel(prompts: List[str], size: str = IMAGE_SIZE, max_workers: int = 3, model: str = None) -> List[Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(generate_single_image, prompt, size, 120, model) for prompt in prompts]
        results = []
        for future in futures:
            try:
                results.append(future.result(timeout=150))
            except Exception as e:
                results.append({"success": False, "error": str(e)})
    return results

def _gen_images_for_segment(image_prompt: str, style: str, model: str = None) -> list:
    """为一个片段生成3张图片，增强 prompt 质量"""
    enhanced = enhance_prompt(image_prompt, style)
    prompts = [f"{enhanced} variation {j+1}" for j in range(3)]
    results = generate_images_parallel(prompts, size=IMAGE_SIZE, max_workers=MAX_CONCURRENT_IMAGES, model=model)
    for r in results:
        if not r.get("success"):
            print(f"  ❌ 单张失败: {r.get('error')}")
        else:
            print(f"  ✅ {r.get('url','')[:60]}...")
    return [r.get("url") if r.get("success") else None for r in results]

def call_ai(prompt, model: str = None, system_prompt="你是一个专业的新媒体内容创作者"):
    if model is None:
        model = DEFAULT_TEXT_MODEL
    headers = {
        "Authorization": f"Bearer {VOLCENGINE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    try:
        response = requests.post(VOLCENGINE_API_URL, headers=headers, json=data, timeout=60)
        result = response.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        raise Exception(f"API调用失败: {result}")
    except Exception as e:
        raise Exception(f"网络请求错误: {str(e)}")

def get_book_intro(book_name):
    search_url = f"https://www.douban.com/j/search?q={book_name}&cat=1001"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        search_result = response.json()
        if search_result.get("items"):
            first_result = search_result["items"][0]
            return first_result.get("title", book_name), first_result.get("abstract", "")[:500]
        return book_name, ""
    except Exception as e:
        print(f"⚠️  获取豆瓣信息失败: {str(e)}")
        return book_name, ""

@app.route("/api/models", methods=["GET"])
def get_models():
    """✅ 新增：返回可用模型列表给前端"""
    return jsonify({
        "text_models": TEXT_MODELS,
        "image_models": IMAGE_MODELS,
        "default_text_model": DEFAULT_TEXT_MODEL,
        "default_image_model": DEFAULT_IMAGE_MODEL,
    })

@app.route("/api/analyze", methods=["POST"])
def analyze_book():
    import concurrent.futures
    data = request.json
    book_name = data.get("book_name", "").strip()
    selected_style = data.get("style", "")

    # ✅ 获取前端选择的模型，无效则降级到默认
    text_model = data.get("text_model", DEFAULT_TEXT_MODEL)
    image_model = data.get("image_model", DEFAULT_IMAGE_MODEL)
    
    if text_model not in TEXT_MODELS:
        text_model = DEFAULT_TEXT_MODEL
    if image_model not in IMAGE_MODELS:
        image_model = DEFAULT_IMAGE_MODEL
    if not book_name:
        return jsonify({"error": "请输入书名"}), 400
    try:
        print(f"📚 正在获取书籍信息: {book_name}")
        title, book_intro = get_book_intro(book_name)

        print(f"🤖 正在AI提取经典片段...")
        extract_prompt = f"""请从以下书籍信息中，提取3个经典、有启发意义、有实践意义的片段。
书名：《{book_name}》
书籍信息：{book_intro if book_intro else '暂无详细信息'}
请按以下JSON格式输出：
[
  {{
    "segment_title": "片段主题标题",
    "segment_content": "具体的片段内容，100-200字，要完整可读",
    "why_useful": "为什么这个片段有价值",
    "image_prompt": "图片生成提示词，中文，15-30字，描述具体场景"
  }},
  ...(共3个片段)
]
要求：输出必须是有效的JSON数组。"""

        system_prompt = """你是一个专业的新媒体内容创作者，精通小红书内容创作。
输出必须严格是有效的JSON数组格式。"""

        segments_text = call_ai(extract_prompt, text_model, system_prompt)
        segments_text = segments_text.replace("```json", "").replace("```", "").strip()
        segments = json.loads(segments_text)

        print(f"🖼️  正在生成配图（模型: {image_model}，每片段并行{MAX_CONCURRENT_IMAGES}张，片段间也并行）...")

        # 每个片段独立生成自己的3张图，多片段之间并行
        image_results_by_segment = {}
        with ThreadPoolExecutor(max_workers=3) as img_executor:
            img_futures = {}
            for idx, seg in enumerate(segments):
                fut = img_executor.submit(
                    _gen_images_for_segment,
                    seg["image_prompt"],
                    selected_style,
                    image_model
                )
                img_futures[fut] = idx

            for fut in concurrent.futures.as_completed(img_futures):
                idx = img_futures[fut]
                urls = fut.result()
                image_results_by_segment[idx] = urls

        for seg_index, segment in enumerate(segments):
            segment["images"] = image_results_by_segment.get(seg_index, [None, None, None])

        successful = sum(
            1 for urls in image_results_by_segment.values()
            for u in urls if u
        )
        print(f"✅ 图片生成完成！成功: {successful}/{len(segments)*3} 张")

        return jsonify({
            "success": True,
            "book_name": title,
            "book_intro": book_intro,
            "segments": segments,
            "total_images": len(segments) * 3,
            "generated_images": successful,
            "text_model_used": text_model,
            "image_model_used": image_model,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "text_model": DEFAULT_TEXT_MODEL,
        "image_model": DEFAULT_IMAGE_MODEL,
    })

@app.route("/api/proxy-image", methods=["GET"])
def proxy_image():
    """代理图片请求，解决跨域问题"""
    image_url = request.args.get("url")
    if not image_url:
        return jsonify({"error": "缺少 url 参数"}), 400
    try:
        resp = requests.get(image_url, headers={
            "User-Agent": "Mozilla/5.0"
        }, timeout=30)
        # 根据实际内容类型返回，或默认 png
        content_type = resp.headers.get("Content-Type", "image/png")
        return resp.content, 200, {"Content-Type": content_type}
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

if __name__ == "__main__":
    print("=" * 50)
    print("📕 书摘小红书助手后端服务")
    print(f"🤖 文本模型: {DEFAULT_TEXT_MODEL}")
    print(f"🎨 图像模型: {DEFAULT_IMAGE_MODEL}")
    print("🌐 访问地址: http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)