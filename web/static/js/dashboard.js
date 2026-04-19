/**
 * dashboard.js - Client-side logic for the Medical Diorama web portal.
 *
 * Monitor panel is singular. X-ray panels are one-per-display, enumerated
 * via elements with data-display-id; all their interactive children are
 * found via data-role="..." inside that panel.
 */

const socket = io();

socket.on("connect", function () {
    console.log("SocketIO connected");
    socket.emit("request_status");
});

socket.on("status_update", function (data) {
    updateMonitorStatus(data);
    updateAllXrayPanels(data);
});

socket.on("disconnect", function () {
    console.log("SocketIO disconnected");
    document.getElementById("monitor-status-text").textContent = "Disconnected";
    document.querySelectorAll(".xray-panel [data-role='status-text']").forEach(function (el) {
        el.textContent = "Disconnected";
    });
});

// =============================================================================
// Patient Monitor
// =============================================================================

function updateMonitorStatus(data) {
    const dot = document.getElementById("monitor-status-dot");
    const text = document.getElementById("monitor-status-text");
    if (data.monitor_running) {
        dot.className = "status-dot active";
        text.textContent = "Running";
    } else {
        dot.className = "status-dot inactive";
        text.textContent = "Stopped";
    }
    document.getElementById("monitor-fps").textContent = data.monitor_fps + " FPS";

    const alarmValue = document.getElementById("alarm-value");
    const alarmStatus = document.getElementById("alarm-status");
    if (data.monitor_alarm) {
        const labels = { hr_high: "HIGH HR", hr_low: "LOW HR", spo2_low: "LOW SpO2" };
        alarmValue.textContent = labels[data.monitor_alarm] || data.monitor_alarm;
        alarmValue.className = "alarm-on";
        alarmStatus.className = "alarm-status alarm-active";
    } else {
        alarmValue.textContent = "None";
        alarmValue.className = "";
        alarmStatus.className = "alarm-status";
    }
}

const hrSlider = document.getElementById("hr-slider");
const hrValue = document.getElementById("hr-value");
hrSlider.addEventListener("input", function () {
    hrValue.textContent = this.value;
});

const spo2Slider = document.getElementById("spo2-slider");
const spo2Value = document.getElementById("spo2-value");
spo2Slider.addEventListener("input", function () {
    spo2Value.textContent = this.value;
});

document.getElementById("apply-vitals-btn").addEventListener("click", function () {
    fetch("/monitor/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            hr: parseInt(hrSlider.value),
            spo2: parseInt(spo2Slider.value),
        }),
    })
        .then((r) => r.json())
        .then((data) => { if (data.error) console.error("Set vitals error:", data.error); })
        .catch((err) => console.error("Set vitals failed:", err));
});

document.querySelectorAll("[data-alarm]").forEach(function (btn) {
    btn.addEventListener("click", function () {
        const alarmType = this.dataset.alarm;
        const alarmValue = alarmType === "clear" ? null : alarmType;
        fetch("/monitor/alarm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ alarm: alarmValue }),
        })
            .then((r) => r.json())
            .then((data) => { if (data.error) console.error("Set alarm error:", data.error); })
            .catch((err) => console.error("Set alarm failed:", err));
    });
});

// =============================================================================
// X-Ray Panels (per-display)
// =============================================================================

function q(panel, role) {
    return panel.querySelector(`[data-role='${role}']`);
}

function updateAllXrayPanels(data) {
    document.querySelectorAll(".xray-panel").forEach(function (panel) {
        updateXrayPanel(panel, data);
    });
}

function updateXrayPanel(panel, data) {
    const id = panel.dataset.displayId;
    const running = data[`${id}_running`];
    const status = data[`${id}_status`];
    const autoPlay = data[`${id}_auto_play`];
    const interval = data[`${id}_interval`];
    const images = data[`${id}_images`] || [];
    const currentIndex = data[`${id}_current_index`] || 0;

    const dot = q(panel, "status-dot");
    const text = q(panel, "status-text");
    if (running) {
        dot.className = "status-dot active";
        text.textContent = status === "no_images" ? "Running (no images)" : "Running";
    } else {
        dot.className = "status-dot inactive";
        text.textContent = "Stopped";
    }

    q(panel, "auto-play-btn").textContent = "Auto-Play: " + (autoPlay ? "ON" : "OFF");

    const intervalSlider = q(panel, "interval-slider");
    if (document.activeElement !== intervalSlider) {
        intervalSlider.value = interval;
        q(panel, "interval-value").textContent = interval;
    }

    updateImageGallery(panel, id, images, currentIndex);
}

function updateImageGallery(panel, id, images, currentIndex) {
    const gallery = q(panel, "image-gallery");
    q(panel, "image-count").textContent = images.length;

    if (images.length === 0) {
        if (gallery.dataset.imageList !== "") {
            gallery.innerHTML = '<p class="no-images-msg">No images uploaded yet.</p>';
            gallery.dataset.imageList = "";
            gallery.dataset.currentIndex = "";
        }
        return;
    }

    const newList = images.join(",");
    const indexChanged = gallery.dataset.currentIndex !== String(currentIndex);
    if (gallery.dataset.imageList === newList && !indexChanged) return;

    gallery.dataset.imageList = newList;
    gallery.dataset.currentIndex = String(currentIndex);

    let html = "";
    for (let i = 0; i < images.length; i++) {
        const isCurrent = i === currentIndex ? " current" : "";
        const name = images[i];
        html += `
            <div class="image-card${isCurrent}" data-index="${i}" data-filename="${name}">
                <img src="/xray/${id}/image/${encodeURIComponent(name)}"
                     alt="${name}" loading="lazy">
                <div class="image-name">${name}</div>
                <button class="delete-btn" title="Remove image">&times;</button>
            </div>
        `;
    }
    gallery.innerHTML = html;

    gallery.querySelectorAll(".image-card").forEach(function (card) {
        card.addEventListener("click", function (e) {
            if (e.target.classList.contains("delete-btn")) return;
            const index = parseInt(this.dataset.index);
            fetch(`/xray/${id}/set-index`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ index: index }),
            }).catch((err) => console.error("Set index failed:", err));
        });
        card.querySelector(".delete-btn").addEventListener("click", function () {
            const filename = card.dataset.filename;
            if (!confirm("Remove " + filename + " from rotation?")) return;
            fetch(`/xray/${id}/${encodeURIComponent(filename)}`, { method: "DELETE" })
                .catch((err) => console.error("Delete failed:", err));
        });
    });
}

function wireXrayPanel(panel) {
    const id = panel.dataset.displayId;

    q(panel, "auto-play-btn").addEventListener("click", function () {
        fetch(`/xray/${id}/toggle-auto`, { method: "POST" })
            .catch((err) => console.error("Toggle auto failed:", err));
    });

    const intervalSlider = q(panel, "interval-slider");
    const intervalValue = q(panel, "interval-value");
    intervalSlider.addEventListener("input", function () {
        intervalValue.textContent = this.value;
    });

    q(panel, "apply-interval-btn").addEventListener("click", function () {
        fetch(`/xray/${id}/set-interval`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ interval: parseInt(intervalSlider.value) }),
        }).catch((err) => console.error("Set interval failed:", err));
    });

    const uploadArea = q(panel, "upload-area");
    const fileInput = q(panel, "file-input");
    const uploadStatus = q(panel, "upload-status");

    uploadArea.addEventListener("click", function () { fileInput.click(); });

    fileInput.addEventListener("change", function () {
        if (this.files.length > 0) uploadFile(id, this.files[0], fileInput, uploadStatus);
    });

    uploadArea.addEventListener("dragover", function (e) {
        e.preventDefault();
        this.classList.add("drag-over");
    });
    uploadArea.addEventListener("dragleave", function () {
        this.classList.remove("drag-over");
    });
    uploadArea.addEventListener("drop", function (e) {
        e.preventDefault();
        this.classList.remove("drag-over");
        if (e.dataTransfer.files.length > 0) {
            uploadFile(id, e.dataTransfer.files[0], fileInput, uploadStatus);
        }
    });
}

function uploadFile(id, file, fileInput, uploadStatus) {
    uploadStatus.textContent = "Uploading " + file.name + "...";
    uploadStatus.className = "upload-status";

    const formData = new FormData();
    formData.append("image", file);

    fetch(`/xray/${id}/upload`, { method: "POST", body: formData })
        .then((r) => r.json())
        .then((data) => {
            if (data.ok) {
                uploadStatus.textContent = "Uploaded: " + data.filename;
                uploadStatus.className = "upload-status success";
            } else {
                uploadStatus.textContent = "Error: " + data.error;
                uploadStatus.className = "upload-status error";
            }
            fileInput.value = "";
        })
        .catch((err) => {
            uploadStatus.textContent = "Upload failed: " + err;
            uploadStatus.className = "upload-status error";
        });
}

document.querySelectorAll(".xray-panel").forEach(wireXrayPanel);

// =============================================================================
// Initial Load
// =============================================================================

fetch("/status")
    .then((r) => r.json())
    .then((data) => {
        hrSlider.value = data.monitor_hr;
        hrValue.textContent = data.monitor_hr;
        spo2Slider.value = data.monitor_spo2;
        spo2Value.textContent = data.monitor_spo2;
        updateMonitorStatus(data);
        updateAllXrayPanels(data);
    })
    .catch((err) => console.error("Initial status fetch failed:", err));
