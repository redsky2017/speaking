import os
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'

import gradio as gr
import edge_tts
import asyncio
import tempfile
import json
import traceback


async def get_voices():
    voices = await edge_tts.list_voices()
    return {f"{v['ShortName']} - {v['Locale']} ({v['Gender']})": v['ShortName'] for v in voices}

async def text_to_speech(text, voice, rate, pitch, output_dir=None, file_name=None):
    """Convert text to speech with specified voice, rate and pitch"""
    if not text.strip():
        return None, "Please enter text to convert."
    if not voice:
        return None, "Please select a voice."
    
    voice_short_name = voice.split(" - ")[0]
    rate_str = f"{rate:+d}%"
    pitch_str = f"{pitch:+d}Hz"
    communicate = edge_tts.Communicate(text, voice_short_name, rate=rate_str, pitch=pitch_str)
    
    # Determine output path
    if output_dir and file_name:
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, file_name)
    else:
        # Use temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            output_path = tmp_file.name
    
    await communicate.save(output_path)
    return output_path, None

async def batch_text_to_speech(json_input, default_voice, default_rate, default_pitch, output_dir="output_audio"):
    """Process batch text-to-speech conversion from JSON input with progress tracking"""
    try:
        # Parse JSON input
        tasks = json.loads(json_input)
        if not isinstance(tasks, list):
            yield None, "Error: JSON input must be a list", [], 0, 0
            return
        
        total_tasks = len(tasks)
        
        # Process each task
        results = []
        generated_files = []
        for i, task in enumerate(tasks):
            # Update progress (0-based to 1-based index)
            current_progress = i + 1
            
            # Validate required fields
            if "text" not in task or "file_name" not in task:
                results.append(f"Error in item {i}: Missing required fields 'text' or 'file_name'")
                # Still yield progress even if there's an error
                yield results, None, generated_files, current_progress, total_tasks
                continue
            
            # Use task-specific settings or defaults
            task_voice = task.get("voice", default_voice)
            task_rate = task.get("rate", default_rate)
            task_pitch = task.get("pitch", default_pitch)
            
            # Generate audio
            audio_path, error = await text_to_speech(
                task["text"],
                task_voice,
                task_rate,
                task_pitch,
                output_dir,
                task["file_name"]
            )
            
            if error:
                results.append(f"Error in item {i}: {error}")
            else:
                results.append(f"Successfully generated: {task['file_name']}")
                generated_files.append(task['file_name'])
            
            # Yield progress after each task
            yield results, None, generated_files, current_progress, total_tasks
        
        # Final yield with complete results
        yield results, None, generated_files, total_tasks, total_tasks
    except json.JSONDecodeError as e:
        yield None, f"JSON parsing error: {str(e)}", [], 0, 0
    except Exception as e:
        yield None, f"Error processing batch: {str(e)}\n{traceback.format_exc()}", [], 0, 0

def create_abbreviation(text, max_length=20):
    """从文本创建缩写文件名，移除特殊字符并限制长度"""
    # 移除特殊字符，只保留字母、数字和空格
    import re
    cleaned_text = re.sub(r'[^\w\s]', '', text)
    # 取前max_length个字符作为基础
    abbreviation = cleaned_text[:max_length].strip()
    # 替换空格为下划线
    abbreviation = abbreviation.replace(' ', '_')
    # 如果文本太短，直接使用
    if not abbreviation:
        abbreviation = "audio"
    return f"{abbreviation}.mp3"

async def tts_interface(text, voice, rate, pitch):
    # 从文本创建缩写文件名
    file_name = create_abbreviation(text)
    # 使用固定的输出目录，与批量处理保持一致
    output_dir = "output_audio"
    # 生成音频，指定输出目录和文件名
    audio, warning = await text_to_speech(text, voice, rate, pitch, output_dir, file_name)
    if warning:
        return audio, gr.Warning(warning)
    return audio, None

async def single_item_interface(json_input, index, default_voice, default_rate, default_pitch):
    """Generate audio for a single item from JSON input"""
    try:
        tasks = json.loads(json_input)
        if not isinstance(tasks, list):
            return None, gr.Warning("Error: JSON input must be a list")
        
        # Validate index
        if index < 0 or index >= len(tasks):
            return None, gr.Warning(f"Error: Index {index} out of range (0-{len(tasks)-1})")
        
        task = tasks[index]
        if "text" not in task or "file_name" not in task:
            return None, gr.Warning("Error: Missing required fields 'text' or 'file_name'")
        
        # Use task-specific settings or defaults
        task_voice = task.get("voice", default_voice)
        task_rate = task.get("rate", default_rate)
        task_pitch = task.get("pitch", default_pitch)
        
        # Generate audio
        audio_path, error = await text_to_speech(
            task["text"],
            task_voice,
            task_rate,
            task_pitch
        )
        
        if error:
            return None, gr.Warning(error)
        return audio_path, None
    except json.JSONDecodeError as e:
        return None, gr.Warning(f"JSON parsing error: {str(e)}")
    except Exception as e:
        return None, gr.Warning(f"Error: {str(e)}")

async def create_demo():
    voices = await get_voices()
    
    # Example JSON for demonstration
    example_json = '''[
        {"text": "Face", "file_name": "word_face.mp3"},
        {"text": "Touch your face.", "file_name": "sent_face.mp3"},
        {"text": "Wash", "file_name": "word_wash.mp3"},
        {"text": "Wash, wash, wash.", "file_name": "sent_wash.mp3"},
        {"text": "Water", "file_name": "word_water.mp3"},
        {"text": "The water is cool.", "file_name": "sent_water.mp3"},
        {"text": "Let's go! Water time.", "file_name": "guide_day2_step1.mp3"},
        {"text": "Touch the water. Cool!", "file_name": "guide_day2_step2.mp3"},
        {"text": "Wash your face. Good job!", "file_name": "guide_day2_step3.mp3"},
        {"text": "(Sound of running water) Splash, splash! Water is cool. Wash, wash, wash your face. Now you are clean!",
         "file_name": "scenario_day2.mp3"},
        {"text": "Bear has a dirty face. He wants to be clean. He goes to the water. Splash, splash. He washes his face. He uses a towel. Rub, rub, rub. Look! Bear has a clean face. Good morning, Bear!",
         "file_name": "story_day2.mp3"}
    ]'''
    
    with gr.Blocks(analytics_enabled=False) as demo:
        gr.Markdown("# 🎙️ Edge TTS Text-to-Speech (批量处理版)")
        
        with gr.Tabs():
            # Single Text Tab
            with gr.Tab("单个文本处理"):
                # 改为左右结构，与批量处理模式保持一致
                with gr.Row():
                    # 左侧面板：输入和参数
                    with gr.Column(scale=1):
                        gr.Markdown("## 输入设置")
                        text_input = gr.Textbox(label="输入文本", lines=5, placeholder="请输入要转换为语音的文本...")
                        
                        gr.Markdown("## 参数设置")
                        # 设置默认语音为en-US-AriaNeural
                        default_voice_value = "en-US-AriaNeural - en-US (Female)" if "en-US-AriaNeural - en-US (Female)" in voices else ""
                        voice_dropdown = gr.Dropdown(choices=[""] + list(voices.keys()), label="选择语音", value=default_voice_value)
                        rate_slider = gr.Slider(minimum=-50, maximum=50, value=0, label="语速调整 (%)", step=1)
                        pitch_slider = gr.Slider(minimum=-20, maximum=20, value=0, label="音调调整 (Hz)", step=1)
                        
                        generate_btn = gr.Button("生成语音", variant="primary")
                        
                        warning_md = gr.Markdown(label="警告", visible=False)
                    
                    # 右侧面板：音频输出
                    with gr.Column(scale=1):
                        gr.Markdown("## 生成的音频")
                        audio_output = gr.Audio(label="当前播放", type="filepath")
                        
                        gr.Markdown("## 处理结果")
                        single_result = gr.Textbox(label="状态信息", interactive=False)
                
                # 定义更新结果的函数
                async def update_with_result(audio, warning):
                    if warning:
                        return audio, warning, "生成失败"
                    return audio, warning, "生成成功"
                
                generate_btn.click(
                    fn=update_with_result,
                    inputs=[audio_output, warning_md],
                    outputs=[audio_output, warning_md, single_result]
                )
                
                # 先调用tts_interface生成音频
                generate_btn.click(
                    fn=tts_interface,
                    inputs=[text_input, voice_dropdown, rate_slider, pitch_slider],
                    outputs=[audio_output, warning_md]
                )
            
            # Batch Processing Tab
            with gr.Tab("批量处理"):
                # Main layout with left and right panels
                with gr.Row():
                    # Left panel: Input and parameters
                    with gr.Column(scale=1):
                        gr.Markdown("## 输入设置")
                        json_input = gr.Textbox(
                            label="JSON输入", 
                            lines=8, 
                            placeholder="请输入JSON格式的文本列表...",
                            value=example_json
                        )
                        
                        with gr.Row():
                            load_example_btn = gr.Button("加载示例JSON")
                            
                        load_example_btn.click(
                            fn=lambda: example_json,
                            inputs=[],
                            outputs=[json_input]
                        )
                        
                        gr.Markdown("## 参数设置")
                        # 设置默认语音为en-US-AriaNeural
                        default_voice_value = "en-US-AriaNeural - en-US (Female)" if "en-US-AriaNeural - en-US (Female)" in voices else ""
                        default_voice = gr.Dropdown(
                            choices=[""] + list(voices.keys()), 
                            label="默认语音", 
                            value=default_voice_value
                        )
                        default_rate = gr.Slider(minimum=-50, maximum=50, value=0, label="默认语速调整 (%)", step=1)
                        default_pitch = gr.Slider(minimum=-20, maximum=20, value=0, label="默认音调调整 (Hz)", step=1)
                        
                        with gr.Row():
                            batch_generate_btn = gr.Button("批量生成所有音频", variant="primary")
                        
                        with gr.Row():
                            item_index = gr.Number(label="项目索引", value=0, precision=0)
                            single_item_btn = gr.Button("生成单个音频")
                        
                        batch_result = gr.Textbox(label="处理结果", lines=3)
                    
                    # Right panel: Audio files and preview
                    with gr.Column(scale=1):
                        gr.Markdown("## 生成的音频文件")
                        # 添加进度显示组件在音频文件列表上方
                        progress_output = gr.Textbox(label="进度", interactive=False, value="0/0")
                        with gr.Row():
                            refresh_btn = gr.Button("刷新文件列表")
                        
                        # Create a list-like interface using a Radio component
                        # Initialize with empty choices but we'll set them right after creation
                        audio_files_list = gr.Radio(
                            choices=[], 
                            label="音频文件",
                            interactive=True,
                            value=None  # Initialize with no selected value
                        )
                        
                        gr.Markdown("## 音频播放器")
                        audio_preview = gr.Audio(label="当前播放", type="filepath")
                        single_audio_output = gr.Audio(label="单个生成的音频", type="filepath")
                        single_warning = gr.Markdown(label="警告", visible=False)
                
                # Event handlers
                def get_audio_files(json_input_str=None):
                    """Get audio files list and return as tuple for choices and value, sorted by JSON order"""
                    files = update_audio_list(json_input=json_input_str)
                    # 使用正确的gr.update方法
                    return gr.update(choices=files, value=files[0] if files else None)
                
                # 使用gr.Generator类型的输出以支持实时进度更新
                async def process_batch_with_progress(json_str, voice, rate, pitch):
                    # 初始化进度显示
                    yield "开始处理...", get_audio_files(json_str), "0/0"
                    
                    # 使用生成器获取每个任务的进度
                    async for results, error, files, current, total in batch_text_to_speech(json_str, voice, rate, pitch):
                        # 格式化结果文本
                        result_text = "\n".join(results) if results else "No results"
                        if error:
                            result_text = error
                        
                        # 更新进度显示并刷新文件列表
                        yield result_text, get_audio_files(json_str), f"{current}/{total}"
                
                # 配置批量生成按钮的事件处理器以支持实时进度更新
                batch_generate_btn.click(
                    fn=process_batch_with_progress,
                    inputs=[json_input, default_voice, default_rate, default_pitch],
                    outputs=[batch_result, audio_files_list, progress_output]
                )
                
                # Update audio preview when a file is selected (clicked)
                audio_files_list.change(
                    fn=lambda file_name: os.path.join("output_audio", file_name) if file_name else None,
                    inputs=[audio_files_list],
                    outputs=[audio_preview]
                )
                
                # Refresh button to update the audio file list
                refresh_btn.click(
                    fn=get_audio_files,
                    inputs=[json_input],
                    outputs=[audio_files_list]
                )
                
                # 在页面加载时初始化音频文件列表
                gr.on(
                    fn=get_audio_files,
                    inputs=[json_input],
                    outputs=[audio_files_list],
                    triggers=[demo.load]
                )
                
                single_item_btn.click(
                    fn=single_item_interface,
                    inputs=[json_input, item_index, default_voice, default_rate, default_pitch],
                    outputs=[single_audio_output, single_warning]
                )
        
        gr.Markdown("使用说明：\n1. 单个文本处理：输入文本，选择语音参数，生成单个音频文件\n2. 批量处理：\n   - 输入JSON格式的文本列表（包含text和file_name字段）\n   - 可选：为每个项目单独设置voice、rate、pitch参数\n   - 点击批量生成按钮生成所有音频（保存在output_audio目录）\n   - 或输入索引生成单个指定音频\n\n音频文件格式说明：支持mp3格式，文件名将按照file_name字段保存。")
    
    return demo

def update_audio_list(output_dir="output_audio", json_input=None):
    """Update the list of available audio files in the output directory, sorted by JSON order if provided"""
    try:
        if not os.path.exists(output_dir):
            return []
        
        # Get all mp3 files in the output directory
        available_files = set(f for f in os.listdir(output_dir) if f.endswith('.mp3'))
        
        # If JSON input is provided, sort files according to JSON order
        if json_input:
            try:
                tasks = json.loads(json_input)
                if isinstance(tasks, list):
                    # Create ordered list based on JSON
                    ordered_files = []
                    for task in tasks:
                        if "file_name" in task and task["file_name"] in available_files:
                            ordered_files.append(task["file_name"])
                            available_files.remove(task["file_name"])
                    # Add any remaining files that weren't in the JSON
                    ordered_files.extend(sorted(available_files))
                    return ordered_files
            except json.JSONDecodeError:
                pass  # If JSON parsing fails, fall back to default sorting
        
        # Default sorting (alphabetical)
        return sorted(available_files)
    except Exception as e:
        print(f"Error updating audio list: {str(e)}")
        return []

async def main():
    demo = await create_demo()
    demo.queue(default_concurrency_limit=50)
    demo.launch()

if __name__ == "__main__":
    asyncio.run(main())