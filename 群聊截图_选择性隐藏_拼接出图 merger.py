import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os

# 尝试导入 tkinterdnd2 用于支持拖拽文件
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

class ProMerger:
    def __init__(self, root):
        self.root = root
        self.root.title("专业长图拼接工具 (最终完整版)")
        self.root.geometry("1200x800")
        
        self.images_data = []
        self.masks = []
        self.user_zoom = None
        self.zoom_scale = 1.0
        self.selected_img_index = -1
        self.selected_mask_id = None
        self.tk_images = []
        
        self.canvas_drag_data = {"x": 0, "y": 0}
        self.is_dragging_canvas = False
        self.mask_drag_data = {"active": False, "index": -1, "start_y": 0, "orig_y": 0, "orig_h": 0, "type": ""}
        self.left_drag_index = -1

        self._setup_ui()
        self.root.bind("<Configure>", self._on_window_resize)
        
        # 绑定键盘删除键用于删除遮罩
        self.root.bind("<Delete>", lambda e: self.delete_selected_mask())
        self.root.bind("<BackSpace>", lambda e: self.delete_selected_mask())

        # 初始化拖拽支持
        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self._on_drop_files)

    def _setup_ui(self):
        top_frame = tk.Frame(self.root, bg="#f0f0f0", height=50)
        top_frame.pack(fill=tk.X, side=tk.TOP)
        top_frame.pack_propagate(False)
        
        # ================= 按钮布局调整开始 =================
        # 左侧按钮区域
        tk.Button(top_frame, text="+ 添加图片", command=self.add_images, bg="#4CAF50", fg="white", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=(10, 5), pady=10)
        tk.Button(top_frame, text="🗑 删除选中图片", command=self.delete_selected, bg="#f44336", fg="white", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=(5, 20), pady=10)
        
        # 右侧按钮区域 (通过从右向左反向pack，实现视觉上的从左到右排列)
        # 1. 生成并保存 (调整为最右侧)
        tk.Button(top_frame, text="生成并保存", command=self.merge_and_save, bg="#2196F3", fg="white", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=(10, 10), pady=10)
        
        # 2. + 添加遮罩 (增加与生成并保存之间的空隙，右侧留出30像素的间隙)
        tk.Button(top_frame, text="+ 添加遮罩", command=self.add_mask, bg="#FF9800", fg="white", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=(5, 30), pady=10)
        
        # 3. 删除选中遮罩
        tk.Button(top_frame, text="删除选中遮罩", command=self.delete_selected_mask, bg="#e91e63", fg="white", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=(5, 5), pady=10)
        
        # 4. 本图遮罩清空
        tk.Button(top_frame, text="本图遮罩清空", command=self.clear_masks, bg="#9E9E9E", fg="white", font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=(10, 5), pady=10)
        # ================= 按钮布局调整结束 =================

        container = tk.Frame(self.root, bg="#cccccc")
        container.pack(fill=tk.BOTH, expand=True)

        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1, uniform='col')
        container.grid_columnconfigure(1, weight=4, uniform='col')

        left_frame = tk.Frame(container, bg="#e0e0e0")
        right_frame = tk.Frame(container, bg="#333333")
        left_frame.grid(row=0, column=0, sticky="nsew")
        right_frame.grid(row=0, column=1, sticky="nsew")

        self.left_canvas = tk.Canvas(left_frame, bg="#e0e0e0", highlightthickness=0)
        self.left_scrollbar = tk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)
        self.left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.left_inner_frame = tk.Frame(self.left_canvas, bg="#e0e0e0")
        self.left_window = self.left_canvas.create_window((0,0), window=self.left_inner_frame, anchor="nw")
        self.left_inner_frame.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))
        self.left_canvas.bind("<Configure>", lambda e: self.left_canvas.itemconfig(self.left_window, width=e.width))
        self.left_canvas.bind_all("<MouseWheel>", self._on_left_mousewheel)

        self.canvas = tk.Canvas(right_frame, bg="#2b2b2b", highlightthickness=0)
        self.v_scroll = tk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = tk.Scrollbar(right_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<MouseWheel>", self._on_right_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Configure>", lambda e: self.refresh_canvas())

    # ---------- 拖拽文件导入支持 ----------
    def _on_drop_files(self, event):
        files = self.root.tk.splitlist(event.data)
        self._process_files(files)

    def add_images(self):
        files = filedialog.askopenfilenames(filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if files:
            self._process_files(files)

    def _process_files(self, files):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp')):
                try:
                    img = Image.open(f).convert("RGB")
                    thumb = img.copy()
                    thumb.thumbnail((180, 300), Image.LANCZOS)
                    tk_thumb = ImageTk.PhotoImage(thumb)
                    self.images_data.append({"path": f, "img": img, "name": os.path.basename(f), "tk_thumb": tk_thumb})
                except Exception as e:
                    messagebox.showerror("错误", f"无法打开 {f}: {e}")
        self.render_left_list()
        if self.selected_img_index == -1 and self.images_data:
            self.select_image(0)

    def select_image(self, index):
        if index < 0 or index >= len(self.images_data): return
        self.selected_img_index = index
        self.selected_mask_id = None
        self.render_left_list()
        self.refresh_canvas()

    def delete_selected(self):
        if self.selected_img_index < 0: return
        idx = self.selected_img_index
        self.masks = [m for m in self.masks if m["img_idx"] != idx]
        for m in self.masks:
            if m["img_idx"] > idx: m["img_idx"] -= 1
        del self.images_data[idx]
        self.selected_img_index = -1
        self.selected_mask_id = None
        self.render_left_list()
        self.refresh_canvas()
        if self.images_data:
            self.select_image(min(idx, len(self.images_data)-1))

    def render_left_list(self):
        for widget in self.left_inner_frame.winfo_children():
            widget.destroy()
        for i, data in enumerate(self.images_data):
            is_selected = (i == self.selected_img_index)
            border_width = 3 if is_selected else 1
            card = tk.Frame(self.left_inner_frame, bg="#e0e0e0", padx=5, pady=5)
            card.pack(fill=tk.X, pady=2)
            lbl = tk.Label(card, image=data["tk_thumb"], bg="white", bd=border_width, relief=tk.SOLID)
            lbl.pack(anchor=tk.CENTER)
            name_lbl = tk.Label(card, text=data["name"], bg="#e0e0e0", font=("微软雅黑", 8), wraplength=160)
            name_lbl.pack(anchor=tk.CENTER, pady=(2,0))
            
            # 绑定点击和拖拽事件（扩大绑定范围）
            for widget in (card, lbl, name_lbl):
                widget.bind("<Button-1>", lambda e, idx=i: self.select_image(idx))
                widget.bind("<B1-Motion>", lambda e, idx=i: self._on_left_drag_motion(idx, e))
                widget.bind("<ButtonRelease-1>", lambda e, idx=i: self._on_left_drag_release(idx, e))

    def _on_left_mousewheel(self, event):
        if self.left_canvas.winfo_containing(event.x_root, event.y_root):
            self.left_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_left_drag_motion(self, index, event):
        if self.left_drag_index == -1:
            self.left_drag_index = index

    def _on_left_drag_release(self, index, event):
        if self.left_drag_index != -1 and self.left_drag_index != index:
            # 重新排序图片
            item = self.images_data.pop(self.left_drag_index)
            self.images_data.insert(index, item)
            
            # 更新选中索引
            if self.selected_img_index == self.left_drag_index:
                self.selected_img_index = index
            elif self.left_drag_index < self.selected_img_index <= index:
                self.selected_img_index -= 1
            elif index <= self.selected_img_index < self.left_drag_index:
                self.selected_img_index += 1
                
            # 更新遮罩索引
            for m in self.masks:
                if m["img_idx"] == self.left_drag_index:
                    m["img_idx"] = index
                elif self.left_drag_index < index and self.left_drag_index < m["img_idx"] <= index:
                    m["img_idx"] -= 1
                elif index < self.left_drag_index and index <= m["img_idx"] < self.left_drag_index:
                    m["img_idx"] += 1
                    
            self.render_left_list()
            self.refresh_canvas()
        self.left_drag_index = -1

    def refresh_canvas(self):
        self.canvas.delete("all")
        self.tk_images = []
        if not self.images_data:
            self.canvas.create_text(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, text="请添加图片...", fill="#666", font=("微软雅黑", 14))
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        max_w = max(img["img"].width for img in self.images_data)
        total_h = sum(img["img"].height for img in self.images_data)
        
        if self.user_zoom is None:
            if cw > 10:
                self.user_zoom = 0.25 * (cw - 40) / max_w
            else:
                self.user_zoom = 0.25
        self.zoom_scale = self.user_zoom
        
        disp_w = int(max_w * self.zoom_scale)
        disp_h = int(total_h * self.zoom_scale)
        offset_x = max(20, (cw - disp_w) // 2) # 避免图片贴边
        offset_y = 20
        y_off = 0
        self.img_rects = []
        for i, data in enumerate(self.images_data):
            img = data["img"]
            single_h = int(img.height * self.zoom_scale)
            resized = img.resize((disp_w, single_h), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(resized)
            self.tk_images.append(tk_img)
            self.canvas.create_image(offset_x, offset_y + y_off, anchor=tk.NW, image=tk_img, tags=f"img_{i}")
            self.img_rects.append({"y": offset_y + y_off, "h": single_h, "img_idx": i, "w": disp_w, "x": offset_x})
            y_off += single_h
        # 更新滚动区域，加入水平滚动
        self.canvas.config(scrollregion=(0, 0, max(cw, disp_w + offset_x*2), offset_y + disp_h + 20))
        self._draw_masks(offset_x, offset_y)

    def _draw_masks(self, img_x, img_y):
        for i, m in enumerate(self.masks):
            img_rect = self.img_rects[m["img_idx"]]
            img_h_px = self.images_data[m["img_idx"]]["img"].height
            my = img_rect["y"] + m["y"] * self.zoom_scale * img_h_px
            mh = m["h"] * self.zoom_scale * img_h_px
            is_sel = (m["id"] == self.selected_mask_id)
            rect_id = self.canvas.create_rectangle(img_x, my, img_x + img_rect["w"], my + mh, fill="#888888", stipple="gray50", outline="red" if is_sel else "", width=2, tags=f"mask_{m['id']}")
            m["rect_id"] = rect_id

    def _get_mask_hover_type(self, event):
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        for i in range(len(self.masks) - 1, -1, -1):
            m = self.masks[i]
            img_rect = self.img_rects[m["img_idx"]]
            img_h_px = self.images_data[m["img_idx"]]["img"].height
            my = img_rect["y"] + m["y"] * self.zoom_scale * img_h_px
            mh = m["h"] * self.zoom_scale * img_h_px
            
            in_x_range = (img_rect["x"] <= canvas_x <= img_rect["x"] + img_rect["w"])
            if in_x_range and my <= canvas_y <= my + mh:
                edge_threshold = 8
                if abs(canvas_y - my) < edge_threshold:
                    return i, "top"
                elif abs(canvas_y - (my + mh)) < edge_threshold:
                    return i, "bottom"
                else:
                    return i, "move"
        return -1, None

    def _on_canvas_motion(self, event):
        if self.mask_drag_data["active"]: return
        idx, hover_type = self._get_mask_hover_type(event)
        if idx != -1:
            if hover_type in ["top", "bottom"]:
                self.canvas.config(cursor="sb_v_double_arrow")
            else:
                self.canvas.config(cursor="fleur")
        else:
            self.canvas.config(cursor="")

    def _on_canvas_press(self, event):
        if not self.images_data: return
        idx, hover_type = self._get_mask_hover_type(event)
        if idx != -1:
            m = self.masks[idx]
            self.selected_mask_id = m["id"]
            self._start_mask_drag(idx, hover_type, event.y, m["y"], m["h"])
            self.refresh_canvas()
            return
        self.selected_mask_id = None
        self.is_dragging_canvas = True
        self.canvas_drag_data["x"] = event.x
        self.canvas_drag_data["y"] = event.y
        self.canvas.config(cursor="hand2")
        self.refresh_canvas()

    def _start_mask_drag(self, index, drag_type, start_y, orig_y, orig_h):
        self.mask_drag_data = {"active": True, "index": index, "type": drag_type, "start_y": start_y, "orig_y": orig_y, "orig_h": orig_h}

    def _on_canvas_drag(self, event):
        if self.mask_drag_data["active"]:
            self._handle_mask_drag(event)
        elif self.is_dragging_canvas:
            dx = event.x - self.canvas_drag_data["x"]
            dy = event.y - self.canvas_drag_data["y"]
            self.canvas.xview_scroll(-dx, "units")
            self.canvas.yview_scroll(-dy, "units")
            self.canvas_drag_data["x"] = event.x
            self.canvas_drag_data["y"] = event.y

    def _handle_mask_drag(self, event):
        if not self.mask_drag_data["active"]: return
        dy = event.y - self.mask_drag_data["start_y"]
        idx = self.mask_drag_data["index"]
        m = self.masks[idx]
        img_h_px = self.images_data[m["img_idx"]]["img"].height
        zoomed_img_h = img_h_px * self.zoom_scale
        ratio_dy = dy / zoomed_img_h
        orig_y = self.mask_drag_data["orig_y"]
        orig_h = self.mask_drag_data["orig_h"]
        
        if self.mask_drag_data["type"] == "move":
            new_y = max(0, min(1 - orig_h, orig_y + ratio_dy))
            self.masks[idx]['y'] = new_y
        elif self.mask_drag_data["type"] == "top":
            new_y = max(0, orig_y + ratio_dy)
            new_h = orig_h - ratio_dy
            if new_h > 0.02:
                self.masks[idx]['y'] = new_y
                self.masks[idx]['h'] = new_h
        elif self.mask_drag_data["type"] == "bottom":
            new_h = max(0.02, orig_h + ratio_dy)
            if (orig_y + new_h) <= 1:
                self.masks[idx]['h'] = new_h
        self.refresh_canvas()

    def _on_canvas_release(self, event):
        self.mask_drag_data["active"] = False
        self.is_dragging_canvas = False
        self.canvas.config(cursor="")
        self._on_canvas_motion(event)

    def add_mask(self):
        if self.selected_img_index < 0:
            messagebox.showwarning("提示", "请先选择图片")
            return
        new_id = f"mask_{len(self.masks)}"
        self.masks.append({"id": new_id, "img_idx": self.selected_img_index, "y": 0.4375, "h": 0.125})
        self.selected_mask_id = new_id
        self.refresh_canvas()

    # ---------- 单独删除选中遮罩 ----------
    def delete_selected_mask(self):
        if self.selected_mask_id:
            self.masks = [m for m in self.masks if m["id"] != self.selected_mask_id]
            self.selected_mask_id = None
            self.refresh_canvas()
        else:
            messagebox.showinfo("提示", "请先在右侧画布中点击选中一个遮罩（边缘出现红线）")

    def clear_masks(self):
        if self.selected_img_index < 0: return
        self.masks = [m for m in self.masks if m["img_idx"] != self.selected_img_index]
        self.selected_mask_id = None
        self.refresh_canvas()

    def _on_right_mousewheel(self, event):
        if not self.canvas.winfo_containing(event.x_root, event.y_root): return
        if event.state & 0x4:
            if not self.images_data: return
            cw = self.canvas.winfo_width()
            max_w = max(img["img"].width for img in self.images_data)
            max_scale = (cw - 40) / max_w if cw > 10 else 1.0
            if event.delta > 0:
                self.user_zoom = min(self.user_zoom * 1.1, max_scale)
            else:
                self.user_zoom = max(self.user_zoom * 0.9, 0.1)
            self.refresh_canvas()
        else:
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_window_resize(self, event):
        if event.widget == self.root:
            self.refresh_canvas()

    # ---------- 图片保存坐标计算逻辑 ----------
    def _get_trimmed_h(self, img_h, masks):
        """计算裁剪掉遮罩部分后的图片实际高度"""
        sorted_masks = sorted(masks, key=lambda x: x['y'])
        last_y = 0
        trimmed_h = 0
        for m in sorted_masks:
            # 使用 max 确保当前遮罩起始位置不会超过上一个遮罩的结束位置
            my = max(last_y, int(m['y'] * img_h))
            mend = max(my, int((m['y'] + m['h']) * img_h))
            trimmed_h += my - last_y
            last_y = max(last_y, mend)
        trimmed_h += img_h - last_y
        return trimmed_h

    def merge_and_save(self):
        if not self.images_data:
            messagebox.showwarning("提示", "没有图片可合并")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if not path: return
        try:
            max_w = max(img["img"].width for img in self.images_data)
            
            # 精确计算总高度
            total_h = 0
            for i, data in enumerate(self.images_data):
                related_masks = [m for m in self.masks if m["img_idx"] == i]
                total_h += self._get_trimmed_h(data["img"].height, related_masks)
            
            result = Image.new('RGB', (max_w, total_h), (255, 255, 255))
            y_off = 0
            
            for i, data in enumerate(self.images_data):
                img = data["img"]
                related_masks = sorted([m for m in self.masks if m["img_idx"] == i], key=lambda x: x['y'])
                last_y = 0
                
                for mask in related_masks:
                    # 确保裁剪的 lower 永远大于等于 upper
                    my = max(last_y, int(mask['y'] * img.height))
                    mend = max(my, int((mask['y'] + mask['h']) * img.height))
                    
                    if my > last_y:
                        part = img.crop((0, last_y, img.width, my))
                        result.paste(part, ((max_w - img.width) // 2, y_off))
                        y_off += my - last_y
                    last_y = max(last_y, mend)
                    
                if last_y < img.height:
                    part = img.crop((0, last_y, img.width, img.height))
                    result.paste(part, ((max_w - img.width) // 2, y_off))
                    y_off += img.height - last_y
            
            result.save(path)
            messagebox.showinfo("成功", f"图片已保存至:\n{path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"发生错误: {str(e)}")

if __name__ == "__main__":
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        print("提示：未安装 tkinterdnd2 库，无法使用拖拽文件导入功能。可通过 pip install tkinterdnd2 安装。")
    
    app = ProMerger(root)
    root.mainloop()
