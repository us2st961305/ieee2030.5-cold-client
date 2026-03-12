"""
Flask application for BMS IEEE 2030.5 Client Web UI.

Minimal control panel with:
- / Dashboard: Status overview, Start/Stop/Reload buttons
- /config: YAML config editor
- /logs: Log viewer
- /notify: IEEE 2030.5 Notification endpoint (POST)
- /browser: IEEE 2030.5 Resource Browser
- /meter: MirrorUsagePoint Management
- /modbus: Modbus ↔ IEEE 2030.5 Mapping
- /data: Data Monitor (Modbus + Meter uploads)

Integrated controls:
- /api/start: Start polling worker + BMSClient + notification server
- /api/stop: Stop all components
- /api/reload: Reload config and apply to all components
- /api/client/*: BMSClient status and control
- /api/data/*: Data recording and history
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
import yaml

from bms_2030_5_client.web.log_buffer import log_buffer
from bms_2030_5_client.web.worker_manager import worker_manager, WorkerState
from bms_2030_5_client.web.notification_server import (
    get_notification_manager,
    init_notification_manager,
    NotificationServerManager,
)
from bms_2030_5_client.web.browser import (
    ResourceBrowser,
    MeterManager,
    MeterConfig,
    SEP2_RESOURCES,
)
from bms_2030_5_client.web.modbus_mapping import (
    mapping_manager,
    MappingManager,
)
from bms_2030_5_client.web.client_manager import (
    client_manager,
    get_client_manager,
    ClientState,
)
from bms_2030_5_client.web.data_recorder import (
    data_recorder,
    get_data_recorder,
)
from bms_2030_5_client.runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_CONFIG_PATH = "config/runtime.yaml"
DEFAULT_TEMPLATE_FOLDER = Path(__file__).parent / "templates"


def create_app(
    config_path: str = DEFAULT_CONFIG_PATH,
    debug: bool = False,
) -> Flask:
    """
    Create Flask application.
    
    Args:
        config_path: Path to runtime configuration file
        debug: Enable debug mode
        
    Returns:
        Configured Flask application
    """
    app = Flask(
        __name__,
        template_folder=str(DEFAULT_TEMPLATE_FOLDER),
    )
    app.config["DEBUG"] = debug
    app.config["CONFIG_PATH"] = config_path
    
    # Logging is configured by cli.py via setup_logging() before create_app().
    # No need to call setup_log_capture() here.
    
    # Configure worker manager
    worker_manager.config_path = Path(config_path)
    
    # Register routes
    register_routes(app)
    
    logger.info(f"Flask app created with config: {config_path}")
    return app


def register_routes(app: Flask) -> None:
    """Register all routes."""
    
    # Get notification manager
    notification_manager = get_notification_manager()
    
    # Subscription manager (lazy loaded)
    subs_manager = None
    
    def get_subs_manager():
        """Get or create subscription manager."""
        nonlocal subs_manager
        if subs_manager is None:
            try:
                from bms_2030_5_client.subs import create_subscription_manager
                config_path = Path(app.config.get("CONFIG_PATH", "config/runtime.yaml"))
                if config_path.exists():
                    config = RuntimeConfig.from_yaml(config_path)
                    subs_manager = create_subscription_manager(config, simulation_mode=True)
            except Exception as e:
                logger.warning(f"Could not create subscription manager: {e}")
        return subs_manager
    
    def load_runtime_config() -> Optional[RuntimeConfig]:
        """Load runtime configuration."""
        config_path = Path(app.config.get("CONFIG_PATH", "config/runtime.yaml"))
        if config_path.exists():
            try:
                return RuntimeConfig.from_yaml(config_path)
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
        return None
    
    # ========================================
    # Dashboard
    # ========================================
    
    @app.route("/")
    def dashboard():
        """Dashboard page - status overview and controls."""
        status = worker_manager.status
        ntfy_status = notification_manager.status
        recent_logs = log_buffer.get_recent(10)
        
        return render_template(
            "dashboard.html",
            status=status,
            ntfy_status=ntfy_status,
            logs=recent_logs,
        )
    
    @app.route("/api/status")
    def api_status():
        """API: Get current worker status."""
        sm = get_subs_manager()
        return jsonify({
            "worker": worker_manager.status.to_dict(),
            "notification_server": notification_manager.status.to_dict(),
            "subscription_manager": sm.stats if sm else None,
        })
    
    @app.route("/api/start", methods=["POST"])
    def api_start():
        """
        API: Start all components.
        
        Starts:
        1. Polling worker
        2. Subscription manager (if subscriptions enabled)
        3. Notification server (if notification_server.enabled)
        """
        results = {
            "worker": False,
            "subscription_manager": False,
            "notification_server": False,
        }
        
        # Load config
        config = load_runtime_config()
        
        # 1. Start polling worker
        results["worker"] = worker_manager.start()
        
        # 2. Start subscription manager
        sm = get_subs_manager()
        if sm:
            enabled_subs = config.get_enabled_subscriptions() if config else []
            if enabled_subs:
                try:
                    # Run async start in thread
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(sm.start())
                    loop.close()
                    results["subscription_manager"] = True
                except Exception as e:
                    logger.error(f"Failed to start subscription manager: {e}")
        
        # 3. Start notification server (if enabled in config)
        if config and config.notification_server.enabled:
            results["notification_server"] = notification_manager.start()
        
        success = any(results.values())
        
        log_buffer.add(
            f"Start requested: worker={results['worker']}, "
            f"subs={results['subscription_manager']}, "
            f"ntfy={results['notification_server']}",
            level="INFO",
            logger_name="web.api",
        )
        
        return jsonify({
            "success": success,
            "results": results,
            "status": worker_manager.status.to_dict(),
        })
    
    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        """
        API: Stop all components.
        
        Stops:
        1. Polling worker
        2. Subscription manager
        3. Notification server
        """
        results = {
            "worker": False,
            "subscription_manager": False,
            "notification_server": False,
        }
        
        # 1. Stop polling worker
        results["worker"] = worker_manager.stop()
        
        # 2. Stop subscription manager
        sm = get_subs_manager()
        if sm:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(sm.stop())
                loop.close()
                results["subscription_manager"] = True
            except Exception as e:
                logger.error(f"Failed to stop subscription manager: {e}")
        
        # 3. Stop notification server
        if notification_manager.is_running:
            results["notification_server"] = notification_manager.stop()
        
        success = any(results.values())
        
        log_buffer.add(
            f"Stop requested: worker={results['worker']}, "
            f"subs={results['subscription_manager']}, "
            f"ntfy={results['notification_server']}",
            level="INFO",
            logger_name="web.api",
        )
        
        return jsonify({
            "success": success,
            "results": results,
            "status": worker_manager.status.to_dict(),
        })
    
    @app.route("/api/reload", methods=["POST"])
    def api_reload():
        """
        API: Reload configuration and apply to all components.
        
        1. Re-read config/runtime.yaml
        2. Reload polling worker
        3. Reload subscription manager (reconcile subscriptions)
        4. Reload notification server config
        """
        results = {
            "config_loaded": False,
            "worker": False,
            "subscription_manager": False,
            "notification_server": False,
        }
        
        # 1. Load new config
        config = load_runtime_config()
        if config:
            results["config_loaded"] = True
        else:
            return jsonify({
                "success": False,
                "error": "Failed to load configuration",
                "results": results,
            })
        
        # 2. Reload polling worker
        results["worker"] = worker_manager.reload()
        
        # 3. Reload subscription manager
        sm = get_subs_manager()
        if sm:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(sm.reload(config))
                loop.close()
                results["subscription_manager"] = True
            except Exception as e:
                logger.error(f"Failed to reload subscription manager: {e}")
        
        # 4. Reload notification server
        notification_manager.reload(config)
        results["notification_server"] = True
        
        log_buffer.add(
            f"Reload completed: worker={results['worker']}, "
            f"subs={results['subscription_manager']}, "
            f"ntfy={results['notification_server']}",
            level="INFO",
            logger_name="web.api",
        )
        
        return jsonify({
            "success": results["config_loaded"],
            "results": results,
            "status": worker_manager.status.to_dict(),
        })
    
    # ========================================
    # IEEE 2030.5 Function Sets Overview
    # ========================================
    
    @app.route("/function-sets")
    def function_sets_page():
        """IEEE 2030.5 Function Sets overview page."""
        # Model statistics
        stats = {
            "total_models": 150,  # Approximate count
            "enum_count": 35,
            "dataclass_count": 85,
            "helper_count": 30,
        }
        
        return render_template(
            "function_sets.html",
            stats=stats,
        )
    
    @app.route("/curves")
    def curves_page():
        """DER Curves management page."""
        return render_template("curves.html")
    
    @app.route("/pricing")
    def pricing_page():
        """Pricing and Tariff management page."""
        return render_template("pricing.html")
    
    @app.route("/prepayment")
    def prepayment_page():
        """Prepayment account management page."""
        return render_template("prepayment.html")
    
    # ========================================
    # Config Editor
    # ========================================
    
    @app.route("/config")
    def config_page():
        """Config editor page."""
        config_path = Path(app.config["CONFIG_PATH"])
        
        content = ""
        error = None
        
        if config_path.exists():
            try:
                content = config_path.read_text(encoding="utf-8")
            except Exception as e:
                error = f"Failed to read config: {e}"
        else:
            error = f"Config file not found: {config_path}"
        
        return render_template(
            "config.html",
            content=content,
            config_path=str(config_path),
            error=error,
        )
    
    @app.route("/api/config/save", methods=["POST"])
    def api_config_save():
        """API: Save config file (write only, no reload)."""
        config_path = Path(app.config["CONFIG_PATH"])
        
        try:
            content = request.json.get("content", "")
            
            # Validate YAML syntax
            parsed = yaml.safe_load(content)
            
            # Validate config semantics
            from bms_2030_5_client.runtime_config import (
                RuntimeConfig, ConfigValidationError,
            )
            warnings: list[str] = []
            try:
                cfg = RuntimeConfig.from_dict(
                    parsed if isinstance(parsed, dict) else {}
                )
                warnings = getattr(cfg, "config_warnings", [])
            except ConfigValidationError as e:
                return jsonify({
                    "success": False,
                    "error": f"Config validation: {e}",
                }), 400
            
            # Ensure directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            config_path.write_text(content, encoding="utf-8")
            
            log_buffer.add(
                f"Configuration saved to {config_path}",
                level="INFO",
                logger_name="web.config",
            )
            
            resp = {"success": True, "message": "Config saved"}
            if warnings:
                resp["warnings"] = warnings
            return jsonify(resp)
            
        except yaml.YAMLError as e:
            return jsonify({"success": False, "error": f"Invalid YAML: {e}"}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/api/config/apply", methods=["POST"])
    def api_config_apply():
        """API: Save config and trigger worker reload."""
        config_path = Path(app.config["CONFIG_PATH"])
        
        try:
            content = request.json.get("content", "")
            
            # Validate YAML syntax
            parsed = yaml.safe_load(content)
            
            # Validate config semantics
            from bms_2030_5_client.runtime_config import (
                RuntimeConfig, ConfigValidationError,
            )
            warnings: list[str] = []
            try:
                cfg = RuntimeConfig.from_dict(
                    parsed if isinstance(parsed, dict) else {}
                )
                warnings = getattr(cfg, "config_warnings", [])
            except ConfigValidationError as e:
                return jsonify({
                    "success": False,
                    "error": f"Config validation: {e}",
                }), 400
            
            # Ensure directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            config_path.write_text(content, encoding="utf-8")
            
            log_buffer.add(
                f"Configuration saved and applying to {config_path}",
                level="INFO",
                logger_name="web.config",
            )
            
            # Reload worker
            worker_manager.reload()
            
            resp = {
                "success": True,
                "message": "Config saved and applied",
                "status": worker_manager.status.to_dict(),
            }
            if warnings:
                resp["warnings"] = warnings
            return jsonify(resp)
            
        except yaml.YAMLError as e:
            return jsonify({"success": False, "error": f"Invalid YAML: {e}"}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    # ========================================
    # Log Viewer
    # ========================================
    
    @app.route("/logs")
    def logs_page():
        """Log viewer page."""
        count = request.args.get("count", 100, type=int)
        logs = log_buffer.get_recent(count)
        
        return render_template(
            "logs.html",
            logs=logs,
            count=count,
            total=len(log_buffer),
        )
    
    @app.route("/api/logs")
    def api_logs():
        """API: Get recent logs."""
        count = request.args.get("count", 100, type=int)
        logs = log_buffer.get_recent(count)
        
        return jsonify({
            "logs": [log.to_dict() for log in logs],
            "total": len(log_buffer),
        })
    
    @app.route("/api/logs/clear", methods=["POST"])
    def api_logs_clear():
        """API: Clear log buffer."""
        log_buffer.clear()
        log_buffer.add("Log buffer cleared", level="INFO", logger_name="web.logs")
        return jsonify({"success": True})
    
    # ========================================
    # Notification Server Endpoint
    # ========================================
    
    @app.route("/notify", methods=["POST"])
    def ntfy_endpoint():
        """
        IEEE 2030.5 Notification endpoint.
        
        Receives POST requests with Notification/NotificationList resources.
        Content-Type: application/sep+xml
        
        Reference: IEEE 2030.5-2023, Table 6 (NotificationList POST Mandatory)
        """
        if not notification_manager.is_running:
            return Response(
                "<error>Notification server not running</error>",
                status=503,
                content_type="application/sep+xml",
            )
        
        content_type = request.content_type or ""
        body = request.get_data()
        
        status_code, response_body = notification_manager.handle_notification_request(
            body=body,
            content_type=content_type,
        )
        
        if status_code == 204:
            return Response("", status=204)
        else:
            return Response(
                response_body,
                status=status_code,
                content_type="application/sep+xml",
            )
    
    # ========================================
    # Notification Server API
    # ========================================
    
    @app.route("/api/notify/status")
    def api_ntfy_status():
        """API: Get notification server status."""
        return jsonify(notification_manager.status.to_dict())
    
    @app.route("/api/notify/start", methods=["POST"])
    def api_ntfy_start():
        """API: Start notification server."""
        success = notification_manager.start()
        log_buffer.add(
            "Notification server start requested" if success else "Notification server already running",
            level="INFO" if success else "WARNING",
            logger_name="web.api",
        )
        return jsonify({
            "success": success,
            "status": notification_manager.status.to_dict(),
        })
    
    @app.route("/api/notify/stop", methods=["POST"])
    def api_ntfy_stop():
        """API: Stop notification server."""
        success = notification_manager.stop()
        log_buffer.add(
            "Notification server stop requested" if success else "Notification server not running",
            level="INFO" if success else "WARNING",
            logger_name="web.api",
        )
        return jsonify({
            "success": success,
            "status": notification_manager.status.to_dict(),
        })

    # ========================================
    # Resource Browser
    # ========================================
    
    # Lazy-loaded browser and meter manager instances
    _browser_instance = None
    _meter_manager_instance = None
    
    def get_browser():
        """Get or create resource browser."""
        nonlocal _browser_instance
        config = load_runtime_config()
        if config and _browser_instance is None:
            _browser_instance = ResourceBrowser(config)
        return _browser_instance
    
    def get_meter_manager():
        """Get or create meter manager."""
        nonlocal _meter_manager_instance
        config = load_runtime_config()
        if config and _meter_manager_instance is None:
            _meter_manager_instance = MeterManager(config)
        return _meter_manager_instance
    
    def is_client_connected() -> bool:
        """Check if BMSClient is connected and available."""
        return (
            client_manager.is_running
            and client_manager.status.ieee2030_5_connected
        )
    
    @app.route("/browser")
    def browser_page():
        """IEEE 2030.5 Resource Browser page."""
        config = load_runtime_config()
        profiles = config.profiles if config else []
        
        # Check if BMSClient provides resources
        client_resources = None
        if is_client_connected():
            client_resources = {
                "edev_href": client_manager.get_edev_href(),
                "der_path": client_manager.get_der_path(),
                "mup_href": client_manager.get_mup_href(),
            }
        
        # Get query params
        resource_id = request.args.get("resource", "")
        custom_path = request.args.get("path", "")
        profile_name = request.args.get("profile", "")
        
        response_data = None
        error = None
        current_path = custom_path
        
        # Determine which path to fetch
        if custom_path:
            current_path = custom_path
        elif resource_id and resource_id in SEP2_RESOURCES:
            current_path = SEP2_RESOURCES[resource_id].path
            current_path = SEP2_RESOURCES[resource_id].path
        
        # Fetch resource if path is set
        if current_path and config:
            browser = get_browser()
            if browser:
                try:
                    loop = asyncio.new_event_loop()
                    response_data = loop.run_until_complete(
                        browser.fetch_and_follow_links(current_path, profile_name or None)
                    )
                    loop.close()
                except Exception as e:
                    error = str(e)
                    logger.error(f"Browser fetch error: {e}")
        
        return render_template(
            "browser.html",
            resources=SEP2_RESOURCES,
            profiles=profiles,
            client_resources=client_resources,
            current_resource=resource_id,
            current_path=current_path,
            current_profile=profile_name or (profiles[0].name if profiles else ""),
            response=response_data,
            error=error,
        )
    
    @app.route("/api/browser/fetch", methods=["POST"])
    def api_browser_fetch():
        """API: Fetch a resource from IEEE 2030.5 server."""
        data = request.json or {}
        path = data.get("path", "/dcap")
        profile_name = data.get("profile", None)
        
        browser = get_browser()
        if not browser:
            return jsonify({"success": False, "error": "No configuration loaded"})
        
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                browser.fetch_and_follow_links(path, profile_name)
            )
            loop.close()
            
            return jsonify({
                "success": True,
                "result": result,
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e),
            })

    # ========================================
    # Meter Management (MirrorUsagePoint)
    # ========================================
    
    @app.route("/meter")
    def meter_page():
        """MirrorUsagePoint management page."""
        config = load_runtime_config()
        profiles = config.profiles if config else []
        
        # Get cached meters from database if available
        meters = []  # Changed to list of dicts for more info
        db_summary = None
        meter_types = []
        
        try:
            from bms_2030_5_client.db import get_database
            db = get_database()
            if db:
                db_summary = db.get_summary()
                # Get all MirrorUsagePoints from database
                all_mups = db.get_all_mirror_usage_points()
                for mup in all_mups:
                    # Get readings for this MUP
                    readings = db.get_readings_by_mup(mup.href)
                    # Get meter types for this MUP
                    mup_types = db.get_meter_types(mup.href)
                    
                    meters.append({
                        "href": mup.href,
                        "mrid": mup.mrid or "N/A",
                        "description": mup.description or "N/A",
                        "device_lfdi": mup.device_lfdi,
                        "post_rate": mup.post_rate,
                        "readings_count": len(readings),
                        "readings": [
                            {
                                "description": r.description,
                                "mrid": r.mrid,
                                "uom": r.uom,
                                "kind": r.kind,
                            }
                            for r in readings
                        ],
                        "meter_types": [t.to_dict() for t in mup_types],
                    })
                
                # Get all meter types
                all_types = db.get_meter_types()
                meter_types = [t.to_dict() for t in all_types]
        except Exception as e:
            logger.debug(f"Could not load meters from database: {e}")
        
        # Also check if BMSClient has a MUP
        client_mup = None
        if is_client_connected():
            client_mup = client_manager.get_mup_href()
            # Check if client MUP is in the list
            client_in_list = any(m["href"] == client_mup for m in meters)
            if client_mup and not client_in_list:
                # Add client MUP to list
                meters.append({
                    "href": client_mup,
                    "mrid": "active",
                    "description": "Active Client MUP",
                    "device_lfdi": "",
                    "post_rate": 0,
                    "readings_count": 0,
                    "readings": [],
                    "meter_types": [],
                })
        
        return render_template(
            "meter.html",
            profiles=profiles,
            meters=meters,
            client_mup=client_mup,
            db_summary=db_summary,
            meter_types=meter_types,
        )
    
    @app.route("/api/meter/create", methods=["POST"])
    def api_meter_create():
        """
        API: Create a new MirrorUsagePoint.
        
        Request body:
        {
            "description": "Battery Meter",
            "device_category": 7,
            "profile": "default"
        }
        """
        data = request.json or {}
        description = data.get("description", "Battery Storage Meter")
        device_category = data.get("device_category", 7)
        profile_name = data.get("profile")
        
        meter_manager = get_meter_manager()
        if not meter_manager:
            return jsonify({"success": False, "error": "No configuration loaded"})
        
        try:
            meter_config = MeterConfig(
                description=description,
                device_category=device_category,
            )
            
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                meter_manager.create_meter(meter_config, profile_name)
            )
            loop.close()
            
            # Save to database if successful
            if result.get("success") and result.get("mup_href"):
                try:
                    from bms_2030_5_client.db import get_database, MirrorUsagePointRecord
                    import time
                    db = get_database()
                    if db:
                        mup_record = MirrorUsagePointRecord(
                            href=result["mup_href"],
                            mrid=result.get("mrid", ""),
                            description=description,
                            device_category=device_category,
                            device_lfdi=result.get("lfdi", ""),
                            post_rate=300,
                            created_at=int(time.time()),
                            updated_at=int(time.time()),
                        )
                        db.save_mirror_usage_point(mup_record)
                        logger.info(f"Saved MirrorUsagePoint to database: {result['mup_href']}")
                except Exception as e:
                    logger.warning(f"Could not save MirrorUsagePoint to database: {e}")
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e),
            })
    
    @app.route("/api/meter/list")
    def api_meter_list():
        """API: Get all meters from database."""
        try:
            from bms_2030_5_client.db import get_database
            db = get_database()
            if not db:
                return jsonify({"success": False, "error": "Database not initialized"})
            
            mups = db.get_all_mirror_usage_points()
            return jsonify({
                "success": True,
                "meters": [
                    {
                        "href": mup.href,
                        "mrid": mup.mrid,
                        "description": mup.description,
                        "device_category": mup.device_category,
                        "post_rate": mup.post_rate,
                        "created_at": mup.created_at,
                    }
                    for mup in mups
                ],
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    @app.route("/api/meter/<path:href>/reading", methods=["POST"])
    def api_meter_add_reading(href: str):
        """
        API: Add a reading to a MirrorUsagePoint.
        
        Request body:
        {
            "reading_type": "soc",
            "value": 8500,
            "multiplier": 0
        }
        """
        data = request.json or {}
        reading_type = data.get("reading_type", "soc")
        value = data.get("value", 0)
        multiplier = data.get("multiplier", 0)
        
        meter_manager = get_meter_manager()
        if not meter_manager:
            return jsonify({"success": False, "error": "No configuration loaded"})
        
        # Normalize href (add leading slash if missing)
        if not href.startswith("/"):
            href = f"/{href}"
        
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                meter_manager.add_reading(href, reading_type, value, multiplier)
            )
            loop.close()
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e),
            })

    # ========================================
    # Database API
    # ========================================
    
    @app.route("/api/db/summary")
    def api_db_summary():
        """API: Get database summary."""
        try:
            from bms_2030_5_client.db import get_database
            db = get_database()
            if not db:
                return jsonify({"success": False, "error": "Database not initialized"})
            
            summary = db.get_summary()
            return jsonify({
                "success": True,
                "summary": summary,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    @app.route("/api/db/resources")
    def api_db_resources():
        """API: Get all resources from database."""
        resource_type = request.args.get("type", "all")
        
        try:
            from bms_2030_5_client.db import get_database
            db = get_database()
            if not db:
                return jsonify({"success": False, "error": "Database not initialized"})
            
            resources = {}
            
            if resource_type in ("all", "end_device"):
                edevs = db.get_all_end_devices()
                resources["end_devices"] = [
                    {"href": e.href, "sfdi": e.sfdi, "lfdi": e.lfdi}
                    for e in edevs
                ]
            
            if resource_type in ("all", "der"):
                ders = db.get_all_ders()
                resources["ders"] = [
                    {"href": d.href, "end_device_href": d.end_device_href, "description": d.description}
                    for d in ders
                ]
            
            if resource_type in ("all", "mup"):
                mups = db.get_all_mirror_usage_points()
                resources["mirror_usage_points"] = [
                    {"href": m.href, "mrid": m.mrid, "description": m.description}
                    for m in mups
                ]
            
            return jsonify({
                "success": True,
                "resources": resources,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    @app.route("/api/db/clear", methods=["POST"])
    def api_db_clear():
        """API: Clear all database data."""
        try:
            from bms_2030_5_client.db import get_database
            db = get_database()
            if not db:
                return jsonify({"success": False, "error": "Database not initialized"})
            
            db.clear_all()
            log_buffer.add(
                "Database cleared",
                level="INFO",
                logger_name="web.db",
            )
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    @app.route("/api/meter/types")
    def api_meter_types():
        """API: Get configured meter types."""
        mup_href = request.args.get("mup_href")
        
        try:
            from bms_2030_5_client.db import get_database
            db = get_database()
            if not db:
                return jsonify({"success": False, "error": "Database not initialized"})
            
            if mup_href:
                types = db.get_meter_types(mup_href)
            else:
                types = db.get_meter_types()
            
            return jsonify({
                "success": True,
                "types": [t.to_dict() for t in types],
                "count": len(types),
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    @app.route("/api/meter/types/clear", methods=["POST"])
    def api_meter_types_clear():
        """API: Clear meter types."""
        data = request.json or {}
        mup_href = data.get("mup_href")
        
        try:
            from bms_2030_5_client.db import get_database
            db = get_database()
            if not db:
                return jsonify({"success": False, "error": "Database not initialized"})
            
            count = db.clear_meter_types(mup_href)
            log_buffer.add(
                f"Cleared {count} meter types",
                level="INFO",
                logger_name="web.meter",
            )
            return jsonify({"success": True, "cleared": count})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ========================================
    # BMSClient API (Automation Integration)
    # ========================================
    
    @app.route("/api/client/status")
    def api_client_status():
        """API: Get BMSClient status."""
        return jsonify(client_manager.status.to_dict())
    
    @app.route("/api/client/start", methods=["POST"])
    def api_client_start():
        """
        API: Start the BMSClient automation.
        
        This starts the full automation:
        - Modbus connection to BMS
        - IEEE 2030.5 connection to server
        - EndDevice registration
        - MirrorUsagePoint creation
        - Periodic status reporting
        - DER control handling
        """
        data = request.json or {}
        config_path = data.get("config_path", "config/config.yaml")
        auto_register = data.get("auto_register", True)
        enable_metering = data.get("enable_metering", True)
        enable_der_control = data.get("enable_der_control", True)
        enable_subscription = data.get("enable_subscription", False)
        
        # Configure and start
        client_manager.configure(
            config_path=config_path,
            auto_register=auto_register,
            enable_metering=enable_metering,
            enable_der_control=enable_der_control,
            enable_subscription=enable_subscription,
        )
        
        success = client_manager.start()
        
        log_buffer.add(
            f"BMSClient start requested: {'success' if success else 'failed'}",
            level="INFO" if success else "WARNING",
            logger_name="web.client",
        )
        
        return jsonify({
            "success": success,
            "status": client_manager.status.to_dict(),
        })
    
    @app.route("/api/client/stop", methods=["POST"])
    def api_client_stop():
        """API: Stop the BMSClient automation."""
        success = client_manager.stop()
        
        log_buffer.add(
            f"BMSClient stop requested: {'success' if success else 'failed'}",
            level="INFO" if success else "WARNING",
            logger_name="web.client",
        )
        
        return jsonify({
            "success": success,
            "status": client_manager.status.to_dict(),
        })
    
    @app.route("/api/client/restart", methods=["POST"])
    def api_client_restart():
        """API: Restart the BMSClient automation."""
        success = client_manager.restart()
        
        log_buffer.add(
            f"BMSClient restart requested: {'success' if success else 'failed'}",
            level="INFO" if success else "WARNING",
            logger_name="web.client",
        )
        
        return jsonify({
            "success": success,
            "status": client_manager.status.to_dict(),
        })
    
    @app.route("/api/client/snapshot")
    def api_client_snapshot():
        """API: Get latest BMS snapshot."""
        snapshot = client_manager.get_latest_snapshot()
        return jsonify({
            "success": snapshot is not None,
            "snapshot": snapshot,
        })
    
    @app.route("/api/client/resources")
    def api_client_resources():
        """API: Get registered IEEE 2030.5 resource paths."""
        return jsonify({
            "edev_href": client_manager.get_edev_href(),
            "der_path": client_manager.get_der_path(),
            "mup_href": client_manager.get_mup_href(),
        })

    @app.route("/api/client/der-control")
    def api_client_der_control():
        """
        API: Get DER control status and statistics.
        
        Returns:
        - Control mode (polling/subscription)
        - FSA/Program/Control poll counts
        - Active controls
        - Simulation mode status
        - Subscription stats (if using subscription mode)
        """
        # Update stats before returning
        client_manager.update_der_control_stats()
        
        status = client_manager.status
        return jsonify({
            "success": True,
            "control_mode": status.control_mode,
            "der_control_count": status.der_control_count,
            "stats": status.der_control_stats,
        })

    @app.route("/api/client/der-control/history")
    def api_client_der_control_history():
        """
        API: Get DER control execution history.
        
        Query params:
        - limit: Maximum number of records (default: 50)
        
        Returns:
        - List of control records with execution details
        """
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        limit = request.args.get("limit", 50, type=int)
        history = get_der_control_history()
        
        return jsonify({
            "success": True,
            "records": history.get_history(limit=limit),
            "stats": history.get_stats(),
            "active_controls": history.get_active_controls(),
        })

    @app.route("/api/client/der-control/history/clear", methods=["POST"])
    def api_client_der_control_history_clear():
        """API: Clear DER control history."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        history = get_der_control_history()
        history.clear_history()
        
        log_buffer.add(
            "DER control history cleared",
            level="INFO",
            logger_name="web.client",
        )
        
        return jsonify({
            "success": True,
            "message": "History cleared",
        })

    # ========================================
    # DER Control Monitor Page
    # ========================================

    @app.route("/der-control")
    def der_control_page():
        """DER Control Monitor page - FSA/DERProgram/DERControl overview."""
        return render_template("der_control.html")
    
    @app.route("/api/der-control/summary")
    def api_der_control_summary():
        """API: Get DER control full summary."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        history = get_der_control_history()
        return jsonify({
            "success": True,
            "data": history.get_full_summary(),
        })
    
    @app.route("/api/der-control/requests")
    def api_der_control_requests():
        """API: Get HTTP request logs."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        limit = request.args.get("limit", 50, type=int)
        include_body = request.args.get("include_body", "false").lower() == "true"
        history = get_der_control_history()
        
        return jsonify({
            "success": True,
            "logs": history.get_request_logs(limit=limit, include_body=include_body),
            "stats": history.get_request_stats(),
        })
    
    @app.route("/api/der-control/requests/<request_id>")
    def api_der_control_request_detail(request_id: str):
        """API: Get single request detail with full body content."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        history = get_der_control_history()
        detail = history.get_request_by_id(request_id)
        
        if detail:
            return jsonify({
                "success": True,
                "request": detail,
            })
        else:
            return jsonify({
                "success": False,
                "error": "Request not found",
            }), 404
    
    @app.route("/api/der-control/fsa")
    def api_der_control_fsa():
        """API: Get FSA records."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        history = get_der_control_history()
        return jsonify({
            "success": True,
            "records": history.get_fsa_records(),
            "active": history.get_active_fsa(),
        })
    
    @app.route("/api/der-control/programs")
    def api_der_control_programs():
        """API: Get DERProgram records."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        history = get_der_control_history()
        return jsonify({
            "success": True,
            "records": history.get_program_records(),
            "active": history.get_active_programs(),
        })
    
    @app.route("/api/der-control/controls")
    def api_der_control_controls():
        """API: Get DERControl records."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        limit = request.args.get("limit", 50, type=int)
        history = get_der_control_history()
        
        return jsonify({
            "success": True,
            "records": history.get_history(limit=limit),
            "stats": history.get_stats(),
            "active": history.get_active_controls(),
        })
    
    @app.route("/api/der-control/clear", methods=["POST"])
    def api_der_control_clear():
        """API: Clear all DER control history."""
        from bms_2030_5_client.web.der_control_history import get_der_control_history
        
        history = get_der_control_history()
        history.clear_history()
        
        log_buffer.add(
            "All DER control history cleared",
            level="INFO",
            logger_name="web.der_control",
        )
        
        return jsonify({
            "success": True,
            "message": "All DER control history cleared",
        })

    # ========================================
    # Data Monitor (Modbus + Meter)
    # ========================================
    
    @app.route("/data")
    def data_monitor_page():
        """Data monitor page - view Modbus and Meter upload data."""
        recorder = get_data_recorder()
        
        return render_template(
            "data_monitor.html",
            stats=recorder.get_statistics(),
            latest_system=recorder.get_latest_system(),
            latest_meter=recorder.get_latest_meter(),
            latest_der=recorder.get_latest_der(),
            rack_ids=list(recorder._latest_racks.keys()),
            meter_history=recorder.get_meter_history(10),
            der_history=recorder.get_der_history(10),
            system_history=recorder.get_system_history(10),
        )
    
    @app.route("/api/data/summary")
    def api_data_summary():
        """API: Get complete data summary."""
        recorder = get_data_recorder()
        return jsonify({
            "success": True,
            **recorder.get_summary(),
        })
    
    @app.route("/api/data/stats")
    def api_data_stats():
        """API: Get data recording statistics."""
        recorder = get_data_recorder()
        return jsonify(recorder.get_statistics())
    
    @app.route("/api/data/system/latest")
    def api_data_system_latest():
        """API: Get latest system data."""
        recorder = get_data_recorder()
        data = recorder.get_latest_system()
        return jsonify({
            "success": data is not None,
            "data": data,
        })
    
    @app.route("/api/data/system/history")
    def api_data_system_history():
        """API: Get system data history."""
        recorder = get_data_recorder()
        count = request.args.get("count", 20, type=int)
        return jsonify({
            "success": True,
            "history": recorder.get_system_history(count),
        })
    
    @app.route("/api/data/rack/<int:rack_id>")
    def api_data_rack(rack_id: int):
        """API: Get latest rack data."""
        recorder = get_data_recorder()
        data = recorder.get_latest_rack(rack_id)
        return jsonify({
            "success": data is not None,
            "data": data,
        })
    
    @app.route("/api/data/racks")
    def api_data_racks():
        """API: Get all latest rack data."""
        recorder = get_data_recorder()
        return jsonify({
            "success": True,
            "racks": recorder.get_latest_racks(),
        })
    
    @app.route("/api/data/meter/latest")
    def api_data_meter_latest():
        """API: Get latest meter upload."""
        recorder = get_data_recorder()
        data = recorder.get_latest_meter()
        return jsonify({
            "success": data is not None,
            "data": data,
        })
    
    @app.route("/api/data/meter/history")
    def api_data_meter_history():
        """API: Get meter upload history."""
        recorder = get_data_recorder()
        count = request.args.get("count", 20, type=int)
        return jsonify({
            "success": True,
            "history": recorder.get_meter_history(count),
        })
    
    @app.route("/api/data/der/latest")
    def api_data_der_latest():
        """API: Get latest DER status."""
        recorder = get_data_recorder()
        data = recorder.get_latest_der()
        return jsonify({
            "success": data is not None,
            "data": data,
        })
    
    @app.route("/api/data/der/history")
    def api_data_der_history():
        """API: Get DER status history."""
        recorder = get_data_recorder()
        count = request.args.get("count", 20, type=int)
        return jsonify({
            "success": True,
            "history": recorder.get_der_history(count),
        })
    
    @app.route("/api/data/clear", methods=["POST"])
    def api_data_clear():
        """API: Clear all recorded data."""
        recorder = get_data_recorder()
        recorder.clear()
        log_buffer.add(
            "Data recorder cleared",
            level="INFO",
            logger_name="web.data",
        )
        return jsonify({"success": True})

