/**
 * dashboard.js - Client-side logic for the Medical Diorama web portal.
 */

const socket = io();
const COLLAPSIBLE_STORAGE_PREFIX = "medical-diorama.collapsible.";

socket.on("connect", function () {
    console.log("SocketIO connected");
    socket.emit("request_status");
});

socket.on("status_update", function (data) {
    updateMonitorStatus(data);
    updateRansomwarePanel(data);
    updateAllXrayPanels(data);
});

socket.on("disconnect", function () {
    console.log("SocketIO disconnected");
    document.getElementById("monitor-status-text").textContent = "Disconnected";
    document.getElementById("ransomware-status-text").textContent = "Disconnected";
    document.querySelectorAll(".xray-panel [data-role='status-text']").forEach(function (el) {
        el.textContent = "Disconnected";
    });
});

function q(scope, role) {
    return scope.querySelector(`[data-role='${role}']`);
}

function setCollapsibleState(section, expanded) {
    const toggle = q(section, "collapsible-toggle");
    const content = q(section, "collapsible-content");
    const icon = toggle.querySelector(".collapsible-icon");

    section.classList.toggle("is-collapsed", !expanded);
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    content.hidden = !expanded;
    icon.textContent = expanded ? "−" : "+";
}

document.querySelectorAll("[data-role='collapsible-section']").forEach(function (section) {
    const toggle = q(section, "collapsible-toggle");
    const storageKey = COLLAPSIBLE_STORAGE_PREFIX + (section.dataset.storageKey || "default");

    toggle.addEventListener("click", function () {
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        const nextExpanded = !expanded;
        setCollapsibleState(section, nextExpanded);
        localStorage.setItem(storageKey, nextExpanded ? "expanded" : "collapsed");
    });

    const savedState = localStorage.getItem(storageKey);
    setCollapsibleState(section, savedState === "expanded");
});

function labelForRansomwareTarget(target) {
    if (target === "monitor") return "Patient Monitor";
    if (target === "xray1") return "X-Ray Display 1";
    if (target === "xray2") return "X-Ray Display 2";
    return target;
}

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
            hr: parseInt(hrSlider.value, 10),
            spo2: parseInt(spo2Slider.value, 10),
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
// Ransomware Panel
// =============================================================================

function updateRansomwarePanel(data) {
    const dot = document.getElementById("ransomware-status-dot");
    const text = document.getElementById("ransomware-status-text");
    const badge = document.getElementById("ransomware-source-badge");
    const toggleBtn = document.getElementById("ransomware-toggle-btn");

    if (data.ransomware_active) {
        dot.className = "status-dot active";
        text.textContent = "Ransomware mode active";
    } else {
        dot.className = "status-dot inactive";
        text.textContent = "Ransomware mode inactive";
    }

    let source = "Dashboard Off";
    if (data.ransomware_gpio_asserted) {
        source = data.ransomware_web_enabled ? "GPIO + Dashboard" : "GPIO";
    } else if (data.ransomware_web_enabled) {
        source = "Dashboard";
    }
    badge.textContent = "Source: " + source;

    if (data.ransomware_gpio_asserted) {
        toggleBtn.textContent = data.ransomware_web_enabled
            ? "Dashboard Override: ON"
            : "Dashboard Override: OFF";
    } else {
        toggleBtn.textContent = data.ransomware_web_enabled
            ? "Disable Ransomware"
            : "Enable Ransomware";
    }

    document.querySelectorAll("[data-ransomware-target]").forEach(function (card) {
        const target = card.dataset.ransomwareTarget;
        updateRansomwareTargetCard(card, target, data[`ransomware_${target}_image`]);
    });
}

function updateRansomwareTargetCard(card, target, filename) {
    const preview = q(card, "preview");
    const deleteBtn = q(card, "delete-btn");
    const currentName = preview.dataset.filename || "";

    deleteBtn.disabled = !filename;

    if (!filename) {
        if (currentName !== "") {
            preview.innerHTML = '<p class="no-images-msg">No ransomware image uploaded.</p>';
            preview.dataset.filename = "";
        }
        return;
    }

    if (currentName === filename) return;

    preview.dataset.filename = filename;
    preview.innerHTML = `
        <img src="/ransomware/${target}/image/${encodeURIComponent(filename)}"
             alt="${filename}" loading="lazy">
        <div class="image-name">${filename}</div>
    `;
}

document.getElementById("ransomware-toggle-btn").addEventListener("click", function () {
    fetch("/ransomware/toggle", { method: "POST" })
        .then((r) => r.json())
        .then((data) => { if (data.error) console.error("Toggle ransomware error:", data.error); })
        .catch((err) => console.error("Toggle ransomware failed:", err));
});

function wireRansomwareTargetCard(card) {
    const target = card.dataset.ransomwareTarget;
    const uploadArea = q(card, "upload-area");
    const fileInput = q(card, "file-input");
    const uploadStatus = q(card, "upload-status");
    const deleteBtn = q(card, "delete-btn");

    uploadArea.addEventListener("click", function () { fileInput.click(); });
    fileInput.addEventListener("change", function () {
        if (this.files.length > 0) {
            uploadRansomwareFile(target, this.files[0], fileInput, uploadStatus);
        }
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
            uploadRansomwareFile(target, e.dataTransfer.files[0], fileInput, uploadStatus);
        }
    });

    deleteBtn.addEventListener("click", function () {
        fetch(`/ransomware/${target}`, { method: "DELETE" })
            .then((r) => r.json())
            .then((data) => { if (data.error) console.error("Delete ransomware image error:", data.error); })
            .catch((err) => console.error("Delete ransomware image failed:", err));
    });
}

function uploadRansomwareFile(target, file, fileInput, uploadStatus) {
    uploadStatus.textContent = "Uploading " + file.name + "...";
    uploadStatus.className = "upload-status";

    const formData = new FormData();
    formData.append("image", file);

    fetch(`/ransomware/${target}/upload`, { method: "POST", body: formData })
        .then((r) => r.json())
        .then((data) => {
            if (data.ok) {
                uploadStatus.textContent = "Uploaded for " + labelForRansomwareTarget(target);
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

document.querySelectorAll("[data-ransomware-target]").forEach(wireRansomwareTargetCard);

// =============================================================================
// X-Ray Panels (per-display)
// =============================================================================

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
        if (status === "disconnected") {
            dot.className = "status-dot warning";
            text.textContent = "Assigned HDMI disconnected";
        } else {
            dot.className = "status-dot active";
        }
        if (status === "ransomware") {
            text.textContent = "Ransomware override";
        } else if (status === "no_images") {
            text.textContent = "Running (no images)";
        } else if (status === "disconnected") {
            text.textContent = "Assigned HDMI disconnected";
        } else {
            text.textContent = "Running";
        }
    } else {
        dot.className = "status-dot inactive";
        text.textContent = "Stopped";
    }

    q(panel, "auto-play-btn").textContent = "Auto-Play: " + (autoPlay ? "ON" : "OFF");

    const intervalSlider = q(panel, "interval-slider");
    const intervalValue = q(panel, "interval-value");
    const intervalDirty = panel.dataset.intervalDirty === "true";
    if (!intervalDirty && document.activeElement !== intervalSlider) {
        intervalSlider.value = interval;
        intervalValue.textContent = interval;
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
            const index = parseInt(this.dataset.index, 10);
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
        panel.dataset.intervalDirty = "true";
        intervalValue.textContent = this.value;
    });

    q(panel, "apply-interval-btn").addEventListener("click", function () {
        fetch(`/xray/${id}/set-interval`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ interval: parseInt(intervalSlider.value, 10) }),
        })
            .then((r) => r.json())
            .then((data) => {
                if (data.error) {
                    console.error("Set interval error:", data.error);
                    return;
                }
                panel.dataset.intervalDirty = "false";
                intervalSlider.value = data.interval;
                intervalValue.textContent = data.interval;
            })
            .catch((err) => console.error("Set interval failed:", err));
    });

    const uploadArea = q(panel, "upload-area");
    const fileInput = q(panel, "file-input");
    const uploadStatus = q(panel, "upload-status");

    uploadArea.addEventListener("click", function () { fileInput.click(); });

    fileInput.addEventListener("change", function () {
        if (this.files.length > 0) uploadXrayFile(id, this.files[0], fileInput, uploadStatus);
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
            uploadXrayFile(id, e.dataTransfer.files[0], fileInput, uploadStatus);
        }
    });
}

function uploadXrayFile(id, file, fileInput, uploadStatus) {
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
        updateRansomwarePanel(data);
        updateAllXrayPanels(data);
    })
    .catch((err) => console.error("Initial status fetch failed:", err));
