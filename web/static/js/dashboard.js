/**
 * dashboard.js - Client-side logic for the Medical Diorama web portal.
 *
 * Handles:
 *   - SocketIO connection for live status updates
 *   - Patient monitor controls (HR, SpO2 sliders, alarm buttons)
 *   - X-ray image upload (click and drag-and-drop)
 *   - X-ray gallery management (thumbnails, delete, select)
 *   - Slideshow controls (auto-play toggle, interval)
 */

// =============================================================================
// SocketIO Connection
// =============================================================================

// Connect to the Flask-SocketIO server
const socket = io();

// When connected, request an immediate status update
socket.on("connect", function () {
    console.log("SocketIO connected");
    socket.emit("request_status");
});

// Handle live status updates from the server (sent every ~1 second)
socket.on("status_update", function (data) {
    updateMonitorStatus(data);
    updateXrayStatus(data);
});

socket.on("disconnect", function () {
    console.log("SocketIO disconnected");
    document.getElementById("monitor-status-text").textContent = "Disconnected";
    document.getElementById("xray-status-text").textContent = "Disconnected";
});

// =============================================================================
// Patient Monitor - Status Updates
// =============================================================================

/**
 * Update the patient monitor section of the dashboard with live data.
 */
function updateMonitorStatus(data) {
    // Update status indicator
    const dot = document.getElementById("monitor-status-dot");
    const text = document.getElementById("monitor-status-text");
    if (data.monitor_running) {
        dot.className = "status-dot active";
        text.textContent = "Running";
    } else {
        dot.className = "status-dot inactive";
        text.textContent = "Stopped";
    }

    // Update FPS display
    document.getElementById("monitor-fps").textContent = data.monitor_fps + " FPS";

    // Update alarm display
    const alarmValue = document.getElementById("alarm-value");
    const alarmStatus = document.getElementById("alarm-status");
    if (data.monitor_alarm) {
        const labels = {
            hr_high: "HIGH HR",
            hr_low: "LOW HR",
            spo2_low: "LOW SpO2",
        };
        alarmValue.textContent = labels[data.monitor_alarm] || data.monitor_alarm;
        alarmValue.className = "alarm-on";
        alarmStatus.className = "alarm-status alarm-active";
    } else {
        alarmValue.textContent = "None";
        alarmValue.className = "";
        alarmStatus.className = "alarm-status";
    }
}

// =============================================================================
// Patient Monitor - Controls
// =============================================================================

// --- HR Slider: show live value as the user drags ---
const hrSlider = document.getElementById("hr-slider");
const hrValue = document.getElementById("hr-value");
hrSlider.addEventListener("input", function () {
    hrValue.textContent = this.value;
});

// --- SpO2 Slider: show live value as the user drags ---
const spo2Slider = document.getElementById("spo2-slider");
const spo2Value = document.getElementById("spo2-value");
spo2Slider.addEventListener("input", function () {
    spo2Value.textContent = this.value;
});

// --- Apply Vitals Button: send HR and SpO2 to the server ---
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
        .then((data) => {
            if (data.error) {
                console.error("Set vitals error:", data.error);
            }
        })
        .catch((err) => console.error("Set vitals failed:", err));
});

// --- Alarm Buttons: trigger or clear alarms ---
document.querySelectorAll("[data-alarm]").forEach(function (btn) {
    btn.addEventListener("click", function () {
        const alarmType = this.dataset.alarm;

        // "clear" means set alarm to null
        const alarmValue = alarmType === "clear" ? null : alarmType;

        fetch("/monitor/alarm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ alarm: alarmValue }),
        })
            .then((r) => r.json())
            .then((data) => {
                if (data.error) {
                    console.error("Set alarm error:", data.error);
                }
            })
            .catch((err) => console.error("Set alarm failed:", err));
    });
});

// =============================================================================
// X-Ray Viewer - Status Updates
// =============================================================================

/**
 * Update the X-ray viewer section of the dashboard with live data.
 */
function updateXrayStatus(data) {
    // Update status indicator
    const dot = document.getElementById("xray-status-dot");
    const text = document.getElementById("xray-status-text");
    if (data.xray_running) {
        dot.className = "status-dot active";
        text.textContent =
            data.xray_status === "no_images" ? "Running (no images)" : "Running";
    } else {
        dot.className = "status-dot inactive";
        text.textContent = "Stopped";
    }

    // Update auto-play button text
    document.getElementById("auto-play-btn").textContent =
        "Auto-Play: " + (data.xray_auto_play ? "ON" : "OFF");

    // Update interval slider (only if the user isn't actively dragging)
    const intervalSlider = document.getElementById("interval-slider");
    if (document.activeElement !== intervalSlider) {
        intervalSlider.value = data.xray_interval;
        document.getElementById("interval-value").textContent = data.xray_interval;
    }

    // Update the image gallery
    updateImageGallery(data.xray_images, data.xray_current_index);
}

// =============================================================================
// X-Ray Viewer - Image Gallery
// =============================================================================

/**
 * Rebuild the image gallery with the current list of images.
 * Highlights the currently displayed image.
 */
function updateImageGallery(images, currentIndex) {
    const gallery = document.getElementById("image-gallery");
    const countEl = document.getElementById("image-count");
    countEl.textContent = images.length;

    // If no images, show placeholder
    if (images.length === 0) {
        gallery.innerHTML = '<p class="no-images-msg">No images uploaded yet.</p>';
        return;
    }

    // Build the gallery HTML
    // Only rebuild if the image list changed (avoids flicker)
    const currentHtml = gallery.dataset.imageList || "";
    const newList = images.join(",");
    const indexChanged = gallery.dataset.currentIndex !== String(currentIndex);

    if (currentHtml !== newList || indexChanged) {
        gallery.dataset.imageList = newList;
        gallery.dataset.currentIndex = String(currentIndex);

        let html = "";
        for (let i = 0; i < images.length; i++) {
            const isCurrent = i === currentIndex ? " current" : "";
            const name = images[i];
            html += `
                <div class="image-card${isCurrent}" data-index="${i}" data-filename="${name}">
                    <img src="/xray/image/${encodeURIComponent(name)}"
                         alt="${name}" loading="lazy">
                    <div class="image-name">${name}</div>
                    <button class="delete-btn" title="Remove image">&times;</button>
                </div>
            `;
        }
        gallery.innerHTML = html;

        // Attach click handlers for selecting and deleting images
        gallery.querySelectorAll(".image-card").forEach(function (card) {
            // Click on card = jump to that image
            card.addEventListener("click", function (e) {
                // Don't jump if they clicked the delete button
                if (e.target.classList.contains("delete-btn")) return;

                const index = parseInt(this.dataset.index);
                fetch("/xray/set-index", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ index: index }),
                }).catch((err) => console.error("Set index failed:", err));
            });

            // Click on delete button = remove image
            card.querySelector(".delete-btn").addEventListener("click", function () {
                const filename = card.dataset.filename;
                if (!confirm("Remove " + filename + " from rotation?")) return;

                fetch("/xray/" + encodeURIComponent(filename), {
                    method: "DELETE",
                }).catch((err) => console.error("Delete failed:", err));
            });
        });
    }
}

// =============================================================================
// X-Ray Viewer - Slideshow Controls
// =============================================================================

// --- Auto-Play Toggle ---
document.getElementById("auto-play-btn").addEventListener("click", function () {
    fetch("/xray/toggle-auto", { method: "POST" }).catch((err) =>
        console.error("Toggle auto failed:", err)
    );
});

// --- Interval Slider: show live value ---
const intervalSlider = document.getElementById("interval-slider");
const intervalValue = document.getElementById("interval-value");
intervalSlider.addEventListener("input", function () {
    intervalValue.textContent = this.value;
});

// --- Apply Interval Button ---
document.getElementById("apply-interval-btn").addEventListener("click", function () {
    fetch("/xray/set-interval", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interval: parseInt(intervalSlider.value) }),
    }).catch((err) => console.error("Set interval failed:", err));
});

// =============================================================================
// X-Ray Viewer - Image Upload
// =============================================================================

const uploadArea = document.getElementById("upload-area");
const fileInput = document.getElementById("file-input");
const uploadStatus = document.getElementById("upload-status");

// Click on the upload area opens the file picker
uploadArea.addEventListener("click", function () {
    fileInput.click();
});

// When a file is selected via the picker, upload it
fileInput.addEventListener("change", function () {
    if (this.files.length > 0) {
        uploadFile(this.files[0]);
    }
});

// --- Drag and drop support ---
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
        uploadFile(e.dataTransfer.files[0]);
    }
});

/**
 * Upload a single image file to the server.
 */
function uploadFile(file) {
    // Show uploading status
    uploadStatus.textContent = "Uploading " + file.name + "...";
    uploadStatus.className = "upload-status";

    // Build the multipart form data
    const formData = new FormData();
    formData.append("image", file);

    fetch("/xray/upload", {
        method: "POST",
        body: formData,
    })
        .then((r) => r.json())
        .then((data) => {
            if (data.ok) {
                uploadStatus.textContent = "Uploaded: " + data.filename;
                uploadStatus.className = "upload-status success";
            } else {
                uploadStatus.textContent = "Error: " + data.error;
                uploadStatus.className = "upload-status error";
            }
            // Clear the file input so the same file can be re-uploaded
            fileInput.value = "";
        })
        .catch((err) => {
            uploadStatus.textContent = "Upload failed: " + err;
            uploadStatus.className = "upload-status error";
        });
}

// =============================================================================
// Initial Load
// =============================================================================

// Fetch the current status on page load (in case SocketIO takes a moment)
fetch("/status")
    .then((r) => r.json())
    .then((data) => {
        // Set slider positions to match current state
        hrSlider.value = data.monitor_hr;
        hrValue.textContent = data.monitor_hr;
        spo2Slider.value = data.monitor_spo2;
        spo2Value.textContent = data.monitor_spo2;
        intervalSlider.value = data.xray_interval;
        intervalValue.textContent = data.xray_interval;

        // Update all status displays
        updateMonitorStatus(data);
        updateXrayStatus(data);
    })
    .catch((err) => console.error("Initial status fetch failed:", err));
