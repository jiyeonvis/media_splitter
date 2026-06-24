"""
PDF & 오디오 도구 (PyQt6)
실행: python3.13 pdf_splitter.py
의존성: pip install pymupdf pyqt6
"""

VERSION = "v1.0.2"
GITHUB_REPO = "jiyeonvis/pdf_splitter"

import os
import sys
import shutil
import tempfile
import threading
import subprocess
import urllib.request
import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QCheckBox, QComboBox,
    QTextEdit, QListWidget, QFileDialog, QMessageBox, QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QCursor

try:
    import fitz
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymupdf"])
    import fitz


# ── ffmpeg & utils ─────────────────────────────────────────────

def get_ffmpeg():
    if hasattr(sys, "_MEIPASS"):
        for name in ("ffmpeg", "ffmpeg.exe"):
            p = Path(sys._MEIPASS) / name
            if p.exists():
                return str(p)
    return "ffmpeg"


def get_mb(path):
    return Path(path).stat().st_size / (1024 * 1024)


# ── PDF 로직 ───────────────────────────────────────────────────

def split_pdf_by_size(src, max_mb, output_dir, log, stop_event=None):
    doc = fitz.open(src)
    total = doc.page_count
    src_mb = get_mb(src)
    estimated = max(1, int(total * (max_mb / src_mb) * 0.85))
    parts, page_idx, part_num = [], 0, 1
    while page_idx < total:
        if stop_event and stop_event.is_set():
            break
        chunk_size = estimated
        while True:
            end = min(page_idx + chunk_size, total)
            chunk = fitz.open()
            chunk.insert_pdf(doc, from_page=page_idx, to_page=end - 1)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp_path = tmp.name
            chunk.save(tmp_path, garbage=4, deflate=True)
            chunk.close()
            chunk_mb = get_mb(tmp_path)
            if chunk_mb <= max_mb or chunk_size == 1:
                break
            os.unlink(tmp_path)
            chunk_size = max(1, int(chunk_size * (max_mb / chunk_mb) * 0.9))
        out_name = f"{Path(src).stem}_part{part_num}.pdf"
        out_path = str(Path(output_dir) / out_name)
        shutil.move(tmp_path, out_path)
        chunk_pages = end - page_idx
        log(f"    → {out_name}  ({chunk_pages}p, {chunk_mb:.1f} MB)", "")
        parts.append(out_path)
        page_idx = end
        part_num += 1
        estimated = max(1, chunk_pages)
    doc.close()
    return parts


def split_pdf_by_pages(src, pages_per_chunk, output_dir, log, stop_event=None):
    doc = fitz.open(src)
    total = doc.page_count
    parts, page_idx, part_num = [], 0, 1
    while page_idx < total:
        if stop_event and stop_event.is_set():
            break
        end = min(page_idx + pages_per_chunk, total)
        chunk = fitz.open()
        chunk.insert_pdf(doc, from_page=page_idx, to_page=end - 1)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
        chunk.save(tmp_path, garbage=4, deflate=True)
        chunk.close()
        chunk_mb = get_mb(tmp_path)
        out_name = f"{Path(src).stem}_part{part_num}.pdf"
        out_path = str(Path(output_dir) / out_name)
        shutil.move(tmp_path, out_path)
        log(f"    → {out_name}  ({end - page_idx}p, {chunk_mb:.1f} MB)", "")
        parts.append(out_path)
        page_idx = end
        part_num += 1
    doc.close()
    return parts


# ── Worker 시그널 ──────────────────────────────────────────────

class WorkerSignals(QObject):
    log      = pyqtSignal(str, str)   # (메시지, 색상태그)
    finished = pyqtSignal()


# ── 베이스 탭 ──────────────────────────────────────────────────

class BaseTab(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_paths = []
        self.selected_folder = None
        self._stop_event = None
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        self._build(layout)

    def _build(self, layout):
        raise NotImplementedError

    # ── 공통 위젯 빌더 ──

    def _input_group(self, ext_filter):
        group = QGroupBox("입력")
        vbox = QVBoxLayout(group)

        btn_row = QHBoxLayout()
        self.btn_folder = QPushButton("📂 폴더 선택")
        self.btn_files  = QPushButton("📄 파일 선택")
        self.chk_recursive = QCheckBox("하위 폴더 포함")
        btn_row.addWidget(self.btn_folder)
        btn_row.addWidget(self.btn_files)
        btn_row.addWidget(self.chk_recursive)
        btn_row.addStretch()

        self.lbl_selected = QLabel("선택된 항목 없음")
        self.lbl_selected.setStyleSheet("color: gray;")

        self.lbl_path = QLabel("")
        self.lbl_path.setStyleSheet("color: #888; font-size: 11px;")
        self.lbl_path.setWordWrap(True)

        lbl_list = QLabel("선택된 파일:")
        self.file_list = QListWidget()
        self.file_list.setFixedHeight(100)
        self.file_list.setFont(QFont("Courier", 10))
        self.file_list.setStyleSheet("""
            QListWidget {
                background: #2a2a2a;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 2px;
            }
            QListWidget::item { padding: 2px 4px; }
            QListWidget::item:selected { background: #3a3a5a; }
        """)

        vbox.addLayout(btn_row)
        vbox.addWidget(self.lbl_selected)
        vbox.addWidget(self.lbl_path)
        vbox.addWidget(lbl_list)
        vbox.addWidget(self.file_list)

        self._last_ext_filter = ext_filter

        self.btn_folder.clicked.connect(lambda: self._pick_folder(ext_filter))
        self.btn_files.clicked.connect(lambda: self._pick_files(ext_filter))
        self.chk_recursive.stateChanged.connect(self._rescan_folder)
        return group

    def _log_widget(self):
        w = QTextEdit()
        w.setReadOnly(True)
        w.setFont(QFont("Courier", 10))
        w.setMinimumHeight(160)
        w.setStyleSheet("QTextEdit { background:#1e1e1e; color:#d4d4d4; border:none; }")
        return w

    def _stop_btn(self):
        btn = QPushButton("⏹ 강제중단")
        btn.setEnabled(False)
        btn.setStyleSheet(
            "QPushButton:enabled { color: #ff5555; }"
        )
        btn.clicked.connect(self._confirm_stop)
        return btn

    def _confirm_stop(self):
        reply = QMessageBox.question(
            self, "중단 확인", "정말로 중단하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes and self._stop_event:
            self._stop_event.set()

    # ── 헬퍼 ──

    def _pick_folder(self, ext_filter):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if not folder:
            return
        exts = self._parse_exts(ext_filter)
        glob = "**/*" if self.chk_recursive.isChecked() else "*"
        paths = [str(p) for p in Path(folder).glob(glob)
                 if p.is_file() and p.suffix.lower() in exts]
        self.selected_paths = paths
        self.selected_folder = folder
        self.lbl_selected.setText(f"폴더 선택됨  ({len(paths)}개 파일)")
        self.lbl_path.setText(folder)
        self._refresh_list(paths)
        self._on_selection_changed()

    def _pick_files(self, ext_filter):
        files, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", ext_filter)
        if not files:
            return
        self.selected_paths = list(files)
        self.selected_folder = None
        self.lbl_selected.setText(f"파일 {len(files)}개 선택됨")
        self.lbl_path.setText("")
        self._refresh_list(files)
        self._on_selection_changed()

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더")
        if folder:
            self.out_edit.setText(folder)

    def _parse_exts(self, ext_filter):
        exts = set()
        if "(" in ext_filter:
            inner = ext_filter.split("(")[1].rstrip(")")
            for part in inner.split():
                exts.add(part.lstrip("*").lower())
        return exts

    def _refresh_list(self, paths):
        self.file_list.clear()
        for p in sorted(paths):
            self.file_list.addItem(Path(p).name)

    def _rescan_folder(self):
        if not self.selected_folder:
            return
        self.lbl_selected.setText("🔄 스캔 중...")
        self.file_list.clear()
        self.btn_folder.setEnabled(False)
        self.btn_files.setEnabled(False)
        self.chk_recursive.setEnabled(False)

        signals = WorkerSignals()

        def work():
            exts = self._parse_exts(self._last_ext_filter)
            glob = "**/*" if self.chk_recursive.isChecked() else "*"
            paths = [str(p) for p in Path(self.selected_folder).glob(glob)
                     if p.is_file() and p.suffix.lower() in exts]
            signals.log.emit("__done__", str(len(paths)))
            for p in sorted(paths):
                signals.log.emit("__item__", str(p))

        def on_msg(msg, data):
            if msg == "__done__":
                self.selected_paths = []
                self.file_list.clear()
                self.lbl_selected.setText(f"폴더 선택됨  ({data}개 파일)")
                self.btn_folder.setEnabled(True)
                self.btn_files.setEnabled(True)
                self.chk_recursive.setEnabled(True)
                self._on_selection_changed()
            elif msg == "__item__":
                self.selected_paths.append(data)
                self.file_list.addItem(Path(data).name)

        signals.log.connect(on_msg)
        threading.Thread(target=work, daemon=True).start()

    def _on_selection_changed(self):
        pass

    def _resolve_out(self, src):
        val = self.out_edit.text()
        if val == "(원본과 동일)":
            return Path(src).parent
        base = Path(val)
        if self.chk_keep.isChecked() and self.selected_folder:
            try:
                rel = Path(src).parent.relative_to(self.selected_folder)
                return base / rel
            except ValueError:
                pass
        return base

    def _append_log(self, log_widget, msg, tag=""):
        colors = {"warn": "#f0a500", "ok": "#4ec94e", "err": "#ff5555", "": "#d4d4d4"}
        color = colors.get(tag, "#d4d4d4")
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        log_widget.append(f'<span style="color:{color};">{safe}</span>')

    def _launch(self, signals, fn, stop_btn, *run_buttons):
        self._stop_event = threading.Event()
        orig_labels = [btn.text() for btn in run_buttons]

        for btn, orig in zip(run_buttons, orig_labels):
            btn.setEnabled(False)
            btn.setText("⏳ 처리 중...")
        stop_btn.setEnabled(True)

        def on_finished():
            for btn, orig in zip(run_buttons, orig_labels):
                btn.setEnabled(True)
                btn.setText(orig)
            stop_btn.setEnabled(False)
            self._stop_event = None

        signals.finished.connect(on_finished)
        threading.Thread(target=fn, daemon=True).start()


# ── 탭 1: PDF 용량 분할 ────────────────────────────────────────

class PdfSizeTab(BaseTab):
    def _build(self, layout):
        layout.addWidget(self._input_group("PDF 파일 (*.pdf)"))

        cfg = QGroupBox("설정")
        grid = QGridLayout(cfg)
        self.mb_edit = QLineEdit("200")
        self.mb_edit.setFixedWidth(70)
        self.out_edit = QLineEdit("(원본과 동일)")
        btn_browse = QPushButton("찾아보기")
        btn_browse.clicked.connect(self._browse_output)
        self.chk_keep   = QCheckBox("하위 폴더 구조 유지")
        self.chk_delete = QCheckBox("분할 후 원본 삭제")
        grid.addWidget(QLabel("최대 크기 (MB):"), 0, 0)
        grid.addWidget(self.mb_edit, 0, 1, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(QLabel("출력 폴더:"), 1, 0)
        grid.addWidget(self.out_edit, 1, 1)
        grid.addWidget(btn_browse, 1, 2)
        grid.addWidget(self.chk_keep, 2, 0, 1, 3)
        grid.addWidget(self.chk_delete, 3, 0, 1, 3)
        layout.addWidget(cfg)

        btn_row = QHBoxLayout()
        self.btn_scan = QPushButton("🔍 스캔")
        self.btn_run  = QPushButton("▶ 분할 시작")
        self.btn_run.setEnabled(False)
        self.btn_stop = self._stop_btn()
        btn_row.addWidget(self.btn_scan)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.log = self._log_widget()
        layout.addWidget(self.log)

        self.btn_scan.clicked.connect(self.scan)
        self.btn_run.clicked.connect(self.run)

    def _on_selection_changed(self):
        self.btn_run.setEnabled(False)

    def scan(self):
        if not self.selected_paths:
            QMessageBox.warning(self, "알림", "먼저 폴더나 파일을 선택하세요.")
            return
        try:
            max_mb = float(self.mb_edit.text())
        except ValueError:
            QMessageBox.critical(self, "오류", "크기는 숫자로 입력하세요.")
            return

        self.log.clear()
        over, ok = [], []
        for p in self.selected_paths:
            mb = get_mb(p)
            (over if mb > max_mb else ok).append((p, mb))
        over.sort(key=lambda x: x[1])
        ok.sort(key=lambda x: x[1])

        self._append_log(self.log, f"── 스캔 결과 (기준: {max_mb} MB) ──")
        if ok:
            self._append_log(self.log, f"✔ 기준 이하 (건너뜀): {len(ok)}개", "ok")
            for p, mb in ok:
                self._append_log(self.log, f"  • {Path(p).name}  ({mb:.1f} MB)", "ok")
        if over:
            self._append_log(self.log, f"\n⚠️  분할 필요: {len(over)}개", "warn")
            for p, mb in over:
                self._append_log(self.log, f"  • {Path(p).name}  ({mb:.1f} MB)", "warn")
        else:
            self._append_log(self.log, "\n✅ 모든 파일이 기준 이하입니다.", "ok")
        self.btn_run.setEnabled(bool(over))

    def run(self):
        try:
            max_mb = float(self.mb_edit.text())
        except ValueError:
            QMessageBox.critical(self, "오류", "크기는 숫자로 입력하세요.")
            return
        targets = [p for p in self.selected_paths if get_mb(p) > max_mb]
        if not targets:
            return

        signals = WorkerSignals()
        signals.log.connect(lambda m, t: self._append_log(self.log, m, t))

        def work():
            stop = self._stop_event
            done = failed = 0
            for i, src in enumerate(targets):
                if stop.is_set():
                    signals.log.emit("\n⏹ 중단됨", "warn")
                    break
                out_dir = self._resolve_out(src)
                out_dir.mkdir(parents=True, exist_ok=True)
                signals.log.emit(f"\n[{i+1}/{len(targets)}] {Path(src).name}", "")
                try:
                    parts = split_pdf_by_size(src, max_mb, out_dir,
                                              lambda m, t: signals.log.emit(m, t),
                                              stop_event=stop)
                    done += 1
                    if self.chk_delete.isChecked() and parts:
                        Path(src).unlink()
                        signals.log.emit("    원본 삭제됨", "warn")
                except Exception as e:
                    signals.log.emit(f"    ❌ 오류: {e}", "err")
                    failed += 1
            signals.log.emit(f"\n── 완료: {done}개 분할, {failed}개 실패 ──", "")
            signals.finished.emit()

        self._launch(signals, work, self.btn_stop, self.btn_scan, self.btn_run)


# ── 탭 2: PDF 페이지 분할 ──────────────────────────────────────

class PdfPageTab(BaseTab):
    def _build(self, layout):
        layout.addWidget(self._input_group("PDF 파일 (*.pdf)"))

        cfg = QGroupBox("설정")
        grid = QGridLayout(cfg)
        self.pages_edit = QLineEdit("50")
        self.pages_edit.setFixedWidth(70)
        self.out_edit   = QLineEdit("(원본과 동일)")
        btn_browse = QPushButton("찾아보기")
        btn_browse.clicked.connect(self._browse_output)
        self.chk_keep   = QCheckBox("하위 폴더 구조 유지")
        self.chk_delete = QCheckBox("분할 후 원본 삭제")
        grid.addWidget(QLabel("페이지 수 (N):"), 0, 0)
        grid.addWidget(self.pages_edit, 0, 1, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(QLabel("출력 폴더:"), 1, 0)
        grid.addWidget(self.out_edit, 1, 1)
        grid.addWidget(btn_browse, 1, 2)
        grid.addWidget(self.chk_keep, 2, 0, 1, 3)
        grid.addWidget(self.chk_delete, 3, 0, 1, 3)
        layout.addWidget(cfg)

        btn_row = QHBoxLayout()
        self.btn_run  = QPushButton("▶ 분할 시작")
        self.btn_stop = self._stop_btn()
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.log = self._log_widget()
        layout.addWidget(self.log)

        self.btn_run.clicked.connect(self.run)

    def run(self):
        if not self.selected_paths:
            QMessageBox.warning(self, "알림", "먼저 폴더나 파일을 선택하세요.")
            return
        try:
            n = int(self.pages_edit.text())
            if n < 1:
                raise ValueError
        except ValueError:
            QMessageBox.critical(self, "오류", "페이지 수는 1 이상의 정수로 입력하세요.")
            return

        signals = WorkerSignals()
        signals.log.connect(lambda m, t: self._append_log(self.log, m, t))
        self.log.clear()

        def work():
            stop = self._stop_event
            done = failed = 0
            for i, src in enumerate(self.selected_paths):
                if stop.is_set():
                    signals.log.emit("\n⏹ 중단됨", "warn")
                    break
                out_dir = self._resolve_out(src)
                out_dir.mkdir(parents=True, exist_ok=True)
                total_p = fitz.open(src).page_count
                signals.log.emit(f"\n[{i+1}/{len(self.selected_paths)}] {Path(src).name}  ({total_p}p)", "")
                try:
                    parts = split_pdf_by_pages(src, n, out_dir,
                                               lambda m, t: signals.log.emit(m, t),
                                               stop_event=stop)
                    done += 1
                    if self.chk_delete.isChecked() and parts:
                        Path(src).unlink()
                        signals.log.emit("    원본 삭제됨", "warn")
                except Exception as e:
                    signals.log.emit(f"    ❌ 오류: {e}", "err")
                    failed += 1
            signals.log.emit(f"\n── 완료: {done}개 분할, {failed}개 실패 ──", "")
            signals.finished.emit()

        self._launch(signals, work, self.btn_stop, self.btn_run)


# ── 탭 3: 오디오 → m4a ────────────────────────────────────────

AUDIO_FILTER = "오디오 파일 (*.mp3 *.wav *.aac *.flac *.ogg *.wma *.m4a)"

class AudioConvertTab(BaseTab):
    def _build(self, layout):
        layout.addWidget(self._input_group(AUDIO_FILTER))

        cfg = QGroupBox("설정")
        grid = QGridLayout(cfg)
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["64k", "96k", "128k", "192k", "256k"])
        self.bitrate_combo.setCurrentText("128k")
        self.out_edit   = QLineEdit("(원본과 동일)")
        btn_browse = QPushButton("찾아보기")
        btn_browse.clicked.connect(self._browse_output)
        self.chk_keep   = QCheckBox("하위 폴더 구조 유지")
        self.chk_delete = QCheckBox("변환 후 원본 삭제")

        BITRATE_HELP = (
            "비트레이트: 1초당 담는 데이터 양. 높을수록 음질 좋고 용량 커요.\n\n"
            "64k  — 음성 통화 수준. 인터뷰 녹음 정도에 충분\n"
            "96k  — 음성 위주 콘텐츠에 적당\n"
            "128k — 기본값. 대부분의 용도에 무난\n"
            "192k — 음악을 어느 정도 품질로 듣고 싶을 때\n"
            "256k — 고음질"
        )
        btn_bitrate_help = QPushButton("❓")
        btn_bitrate_help.setToolTip(BITRATE_HELP)
        btn_bitrate_help.setFixedSize(24, 24)
        btn_bitrate_help.setStyleSheet(
            "QPushButton { border: none; background: transparent; font-size: 14px; }"
            "QPushButton:hover { color: #aaa; }"
        )
        btn_bitrate_help.clicked.connect(
            lambda: QToolTip.showText(QCursor.pos(), BITRATE_HELP, btn_bitrate_help)
        )
        bitrate_row = QHBoxLayout()
        bitrate_row.addWidget(self.bitrate_combo)
        bitrate_row.addWidget(btn_bitrate_help)
        bitrate_row.addStretch()
        grid.addWidget(QLabel("비트레이트:"), 0, 0)
        grid.addLayout(bitrate_row, 0, 1)
        grid.addWidget(QLabel("출력 폴더:"), 1, 0)
        grid.addWidget(self.out_edit, 1, 1)
        grid.addWidget(btn_browse, 1, 2)
        grid.addWidget(self.chk_keep, 2, 0, 1, 3)
        grid.addWidget(self.chk_delete, 3, 0, 1, 3)
        layout.addWidget(cfg)

        btn_row = QHBoxLayout()
        self.btn_run  = QPushButton("▶ 변환 시작")
        self.btn_stop = self._stop_btn()
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.log = self._log_widget()
        layout.addWidget(self.log)

        self.btn_run.clicked.connect(self.run)

    def run(self):
        if not self.selected_paths:
            QMessageBox.warning(self, "알림", "먼저 폴더나 파일을 선택하세요.")
            return

        ffmpeg = get_ffmpeg()
        bitrate = self.bitrate_combo.currentText()
        signals = WorkerSignals()
        signals.log.connect(lambda m, t: self._append_log(self.log, m, t))
        self.log.clear()

        def get_duration(path):
            result = subprocess.run(
                [ffmpeg, "-i", str(path)], capture_output=True, text=True, errors="replace"
            )
            for line in result.stderr.split("\n"):
                if "Duration" in line:
                    t = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = t.split(":")
                    return float(h) * 3600 + float(m) * 60 + float(s)
            return None

        def work():
            stop = self._stop_event
            done = failed = skipped = 0
            for i, src in enumerate(self.selected_paths):
                if stop.is_set():
                    signals.log.emit("\n⏹ 중단됨", "warn")
                    break
                if Path(src).suffix.lower() == ".m4a":
                    signals.log.emit(f"[건너뜀] {Path(src).name}  (이미 m4a)", "ok")
                    skipped += 1
                    continue
                out_dir = self._resolve_out(src)
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / (Path(src).stem + ".m4a")
                signals.log.emit(f"\n[{i+1}/{len(self.selected_paths)}] {Path(src).name}", "")
                try:
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_in  = Path(tmp_dir) / f"input{Path(src).suffix}"
                        tmp_out = Path(tmp_dir) / "output.m4a"
                        shutil.copy2(src, tmp_in)
                        total_dur = get_duration(tmp_in)
                        proc = subprocess.Popen(
                            [ffmpeg, "-y", "-i", str(tmp_in),
                             "-c:a", "aac", "-b:a", bitrate,
                             "-progress", "pipe:2", "-nostats", str(tmp_out)],
                            stderr=subprocess.PIPE,
                            text=True, errors="replace"
                        )
                        stderr_lines = []
                        for line in proc.stderr:
                            if stop.is_set():
                                proc.terminate()
                                proc.wait()
                                break
                            stderr_lines.append(line)
                        proc.wait()
                        if stop.is_set():
                            signals.log.emit("\n⏹ 중단됨", "warn")
                            break
                        if proc.returncode == 0:
                            shutil.move(str(tmp_out), str(out_path))
                            signals.log.emit(f"    → {out_path.name}  ({get_mb(out_path):.1f} MB)", "")
                            done += 1
                            if self.chk_delete.isChecked():
                                Path(src).unlink()
                                signals.log.emit("    원본 삭제됨", "warn")
                        else:
                            err = "".join(stderr_lines)[-200:]
                            signals.log.emit(f"    ❌ 오류: {err}", "err")
                            failed += 1
                except FileNotFoundError:
                    signals.log.emit("    ❌ ffmpeg을 찾을 수 없습니다.", "err")
                    failed += 1
            signals.log.emit(f"\n── 완료: {done}개 변환, {skipped}개 건너뜀, {failed}개 실패 ──", "")
            signals.finished.emit()

        self._launch(signals, work, self.btn_stop, self.btn_run)


# ── 탭 4: 오디오 용량 분할 ────────────────────────────────────

class AudioSplitTab(BaseTab):
    def _build(self, layout):
        layout.addWidget(self._input_group(AUDIO_FILTER))

        cfg = QGroupBox("설정")
        grid = QGridLayout(cfg)
        self.mb_edit  = QLineEdit("100")
        self.mb_edit.setFixedWidth(70)
        self.out_edit = QLineEdit("(원본과 동일)")
        btn_browse = QPushButton("찾아보기")
        btn_browse.clicked.connect(self._browse_output)
        self.chk_keep   = QCheckBox("하위 폴더 구조 유지")
        self.chk_delete = QCheckBox("분할 후 원본 삭제")
        grid.addWidget(QLabel("최대 크기 (MB):"), 0, 0)
        grid.addWidget(self.mb_edit, 0, 1, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(QLabel("출력 폴더:"), 1, 0)
        grid.addWidget(self.out_edit, 1, 1)
        grid.addWidget(btn_browse, 1, 2)
        grid.addWidget(self.chk_keep, 2, 0, 1, 3)
        grid.addWidget(self.chk_delete, 3, 0, 1, 3)
        layout.addWidget(cfg)

        btn_row = QHBoxLayout()
        self.btn_run  = QPushButton("▶ 분할 시작")
        self.btn_stop = self._stop_btn()
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.log = self._log_widget()
        layout.addWidget(self.log)

        self.btn_run.clicked.connect(self.run)

    def run(self):
        if not self.selected_paths:
            QMessageBox.warning(self, "알림", "먼저 폴더나 파일을 선택하세요.")
            return
        try:
            max_mb = float(self.mb_edit.text())
        except ValueError:
            QMessageBox.critical(self, "오류", "크기는 숫자로 입력하세요.")
            return

        ffmpeg = get_ffmpeg()
        targets = [p for p in self.selected_paths if get_mb(p) > max_mb]
        if not targets:
            QMessageBox.information(self, "알림", "분할이 필요한 파일이 없습니다.")
            return

        signals = WorkerSignals()
        signals.log.connect(lambda m, t: self._append_log(self.log, m, t))
        self.log.clear()

        def get_duration(tmp_src):
            result = subprocess.run(
                [ffmpeg, "-i", str(tmp_src)], capture_output=True, text=True, errors="replace"
            )
            for line in result.stderr.split("\n"):
                if "Duration" in line:
                    t = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = t.split(":")
                    return float(h) * 3600 + float(m) * 60 + float(s)
            return None

        def work():
            stop = self._stop_event
            done = failed = 0
            for i, src in enumerate(targets):
                if stop.is_set():
                    signals.log.emit("\n⏹ 중단됨", "warn")
                    break
                out_dir = self._resolve_out(src)
                out_dir.mkdir(parents=True, exist_ok=True)
                signals.log.emit(f"\n[{i+1}/{len(targets)}] {Path(src).name}  ({get_mb(src):.1f} MB)", "")
                try:
                    ext = Path(src).suffix.lower()
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_in = Path(tmp_dir) / f"input{ext}"
                        shutil.copy2(src, tmp_in)
                        duration = get_duration(tmp_in)
                        if not duration:
                            raise ValueError("재생 시간을 읽을 수 없습니다.")
                        secs = int(duration * (max_mb / get_mb(src)) * 0.9)
                        part_num, start = 1, 0
                        while start < duration:
                            if stop.is_set():
                                break
                            end = min(start + secs, duration)
                            tmp_out = Path(tmp_dir) / f"part{part_num}{ext}"
                            subprocess.run(
                                [ffmpeg, "-y", "-i", str(tmp_in), "-ss", str(start),
                                 "-to", str(end), "-c", "copy", str(tmp_out)],
                                capture_output=True
                            )
                            out_name = f"{Path(src).stem}_part{part_num}{ext}"
                            out_path = out_dir / out_name
                            shutil.move(str(tmp_out), str(out_path))
                            signals.log.emit(f"    → {out_name}  ({get_mb(out_path):.1f} MB)", "")
                            start = end
                            part_num += 1
                    if stop.is_set():
                        signals.log.emit("\n⏹ 중단됨", "warn")
                        break
                    done += 1
                    if self.chk_delete.isChecked():
                        Path(src).unlink()
                        signals.log.emit("    원본 삭제됨", "warn")
                except FileNotFoundError:
                    signals.log.emit("    ❌ ffmpeg을 찾을 수 없습니다.", "err")
                    failed += 1
                except Exception as e:
                    signals.log.emit(f"    ❌ 오류: {e}", "err")
                    failed += 1
            signals.log.emit(f"\n── 완료: {done}개 분할, {failed}개 실패 ──", "")
            signals.finished.emit()

        self._launch(signals, work, self.btn_stop, self.btn_run)


# ── 메인 윈도우 ────────────────────────────────────────────────

class MainWindow(QMainWindow):
    _update_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PDF & 오디오 도구  {VERSION}")
        self.setMinimumWidth(560)
        self._update_info = None
        self._update_signal.connect(self._show_update_dialog)

        tabs = QTabWidget()
        tabs.addTab(PdfSizeTab(),      "  PDF 용량 분할  ")
        tabs.addTab(PdfPageTab(),      "  PDF 페이지 분할  ")
        tabs.addTab(AudioConvertTab(), "  오디오 → m4a  ")
        tabs.addTab(AudioSplitTab(),   "  오디오 용량 분할  ")
        tabs.setContentsMargins(8, 8, 8, 8)
        self.setCentralWidget(tabs)

        threading.Thread(target=self._check_update, daemon=True).start()

    def _check_update(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "pdf-splitter"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            latest = data.get("tag_name", "")
            if latest and latest != VERSION:
                release_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")
                self._update_info = (latest, release_url)
                self._update_signal.emit()
        except Exception:
            pass

    def _show_update_dialog(self):
        latest, url = self._update_info
        msg = QMessageBox(self)
        msg.setWindowTitle("업데이트 알림")
        msg.setText(f"새 버전이 있습니다: <b>{latest}</b><br><br>"
                    f"현재 버전: {VERSION}<br><br>"
                    f"<a href='{url}'>다운로드 페이지 열기</a>")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
