// Container Scanner Module - Uses Trivy for vulnerability scanning
// Scans Docker containers and reports vulnerabilities to central analysis service

use anyhow::{Result, Context};
use chrono::Utc;
use serde::Deserialize;
use std::process::Command;
use tracing::{info, warn, error};

use super::types::{ContainerScanResult, Vulnerability};

/// Trivy JSON output structures
#[derive(Debug, Deserialize)]
struct TrivyOutput {
    #[serde(rename = "Results")]
    results: Option<Vec<TrivyResult>>,
}

#[derive(Debug, Deserialize)]
struct TrivyResult {
    #[serde(rename = "Target")]
    target: String,
    #[serde(rename = "Vulnerabilities")]
    vulnerabilities: Option<Vec<TrivyVulnerability>>,
}

#[derive(Debug, Deserialize)]
struct TrivyVulnerability {
    #[serde(rename = "VulnerabilityID")]
    vulnerability_id: String,
    #[serde(rename = "PkgName")]
    pkg_name: String,
    #[serde(rename = "InstalledVersion")]
    installed_version: String,
    #[serde(rename = "FixedVersion")]
    fixed_version: Option<String>,
    #[serde(rename = "Severity")]
    severity: String,
    #[serde(rename = "Description")]
    description: Option<String>,
    #[serde(rename = "PrimaryURL")]
    primary_url: Option<String>,
}

pub struct ContainerScanner {
    hostname: String,
}

impl ContainerScanner {
    pub fn new() -> Self {
        let hostname = hostname::get()
            .map(|h| h.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string());
        
        ContainerScanner { hostname }
    }

    /// Get list of running Docker containers
    fn get_running_containers(&self) -> Result<Vec<String>> {
        let output = Command::new("docker")
            .args(["ps", "--format", "{{.Names}}"])
            .output()
            .context("Failed to execute docker ps")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(anyhow::anyhow!("docker ps failed: {}", stderr));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        let containers: Vec<String> = stdout
            .lines()
            .filter(|line| !line.is_empty())
            .map(|s| s.to_string())
            .collect();

        Ok(containers)
    }

    /// Scan a single container with Trivy
    pub fn scan_container(&self, container_name: &str) -> ContainerScanResult {
        let scan_id = format!(
            "scan-{}-{}",
            Utc::now().format("%Y%m%d%H%M%S"),
            &container_name[..container_name.len().min(20)]
        );
        let started_at = Utc::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();

        info!("Scanning container {} with Trivy...", container_name);

        // Run Trivy scan
        let output = Command::new("trivy")
            .args([
                "container",
                "--format", "json",
                "--no-progress",
                "--quiet",
                container_name,
            ])
            .output();

        let (vulnerabilities, score, error, status) = match output {
            Ok(output) if output.status.success() => {
                let stdout = String::from_utf8_lossy(&output.stdout);
                match self.parse_trivy_output(&stdout) {
                    Ok((vulns, score)) => {
                        info!(
                            "Trivy scan complete for {}: {} vulnerabilities, score: {}",
                            container_name,
                            vulns.len(),
                            score
                        );
                        (vulns, score, None, "completed".to_string())
                    }
                    Err(e) => {
                        warn!("Failed to parse Trivy output for {}: {}", container_name, e);
                        (vec![], 100, Some(format!("Parse error: {}", e)), "completed".to_string())
                    }
                }
            }
            Ok(output) => {
                let stderr = String::from_utf8_lossy(&output.stderr);
                error!("Trivy scan failed for {}: {}", container_name, stderr);
                (vec![], 0, Some(stderr.to_string()), "failed".to_string())
            }
            Err(e) => {
                error!("Failed to execute Trivy for {}: {}", container_name, e);
                (vec![], 0, Some(e.to_string()), "failed".to_string())
            }
        };

        let completed_at = Utc::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();

        ContainerScanResult {
            id: scan_id,
            hostname: self.hostname.clone(),
            target: container_name.to_string(),
            scan_type: "vulnerability".to_string(),
            status,
            started_at,
            completed_at: Some(completed_at),
            vulnerabilities,
            score,
            error,
        }
    }

    /// Parse Trivy JSON output
    fn parse_trivy_output(&self, json_str: &str) -> Result<(Vec<Vulnerability>, u8)> {
        let trivy_output: TrivyOutput = serde_json::from_str(json_str)
            .context("Failed to parse Trivy JSON")?;

        let mut vulnerabilities = Vec::new();
        let mut score: i32 = 100;

        if let Some(results) = trivy_output.results {
            for result in results {
                if let Some(vulns) = result.vulnerabilities {
                    for (idx, v) in vulns.iter().enumerate() {
                        let vuln_id = format!("vuln-{}-{}", v.vulnerability_id, idx);
                        
                        vulnerabilities.push(Vulnerability {
                            id: vuln_id,
                            cve_id: Some(v.vulnerability_id.clone()),
                            severity: v.severity.to_lowercase(),
                            package: v.pkg_name.clone(),
                            version: v.installed_version.clone(),
                            fixed_version: v.fixed_version.clone(),
                            description: v.description.clone().unwrap_or_default(),
                            link: v.primary_url.clone(),
                        });

                        // Calculate score deduction
                        match v.severity.to_lowercase().as_str() {
                            "critical" => score -= 25,
                            "high" => score -= 15,
                            "medium" => score -= 5,
                            "low" => score -= 2,
                            _ => {}
                        }
                    }
                }
            }
        }

        Ok((vulnerabilities, score.max(0) as u8))
    }

    /// Scan all running containers
    pub fn scan_all_containers(&self) -> Vec<ContainerScanResult> {
        let mut results = Vec::new();

        match self.get_running_containers() {
            Ok(containers) => {
                info!("Found {} running containers to scan", containers.len());
                for container in containers {
                    let result = self.scan_container(&container);
                    results.push(result);
                }
            }
            Err(e) => {
                error!("Failed to get running containers: {}", e);
            }
        }

        results
    }
}
