<#
.SYNOPSIS
    Deploys the AI News to LinkedIn Agent to Azure Container Apps (ACA) using Docker Hub.

.DESCRIPTION
    1. Builds and pushes the container image to Docker Hub.
    2. Provisions an Azure Resource Group, Azure Storage Account, and Azure File Share for persistent state.
    3. Provisions an Azure Container Apps Environment with the storage volume mounted.
    4. Deploys the container app as a 24/7 background worker (min-replicas=1, max-replicas=1, ingress disabled).
    5. Injects environment variables securely from .env into Azure Container Apps Secrets.

.PARAMETER DockerUsername
    Your Docker Hub username (e.g. 'avpansmw').

.PARAMETER Location
    Azure region (default: 'eastus').
#>

param (
    [Parameter(Mandatory=$false)]
    [string]$DockerUsername,

    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus",

    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "rg-linkedin-bot",

    [Parameter(Mandatory=$false)]
    [string]$AppName = "ca-linkedin-bot",

    [Parameter(Mandatory=$false)]
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🚀 Deploying LinkedIn Bot to Azure Container Apps (ACA)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verify Azure CLI login
Write-Host "`n[1/6] Checking Azure CLI authentication..." -ForegroundColor Yellow
$azAccount = az account show --output json 2>$null | ConvertFrom-Json
if (-not $azAccount) {
    Write-Host "❌ Not logged into Azure CLI. Running 'az login'..." -ForegroundColor Red
    az login
    $azAccount = az account show --output json | ConvertFrom-Json
}
Write-Host "✅ Authenticated as: $($azAccount.user.name) (Subscription: $($azAccount.name))" -ForegroundColor Green

# 2. Verify Docker Hub Username
if (-not $DockerUsername) {
    $DockerUsername = Read-Host "`nEnter your Docker Hub username"
}
if (-not $DockerUsername) {
    Write-Error "Docker Hub username is required."
}

$ImageTag = "$DockerUsername/linkedin-bot:latest"

# 3. Build & Push Docker Image
if ($SkipBuild) {
    Write-Host "`n[2/6] Skipping local Docker build & push (using existing $ImageTag)..." -ForegroundColor Yellow
} else {
    Write-Host "`n[2/6] Building and pushing Docker image to Docker Hub ($ImageTag)..." -ForegroundColor Yellow

    try {
        docker info > $null 2>&1
    } catch {
        Write-Host "❌ Docker Desktop is not running. Please start Docker Desktop and retry." -ForegroundColor Red
        exit 1
    }

    docker build -t $ImageTag .
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed."
    }

    Write-Host "Pushing image to Docker Hub..." -ForegroundColor Yellow
    docker push $ImageTag
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️ If push failed, make sure you ran 'docker login' first." -ForegroundColor Red
        Write-Error "Docker push failed."
    }
    Write-Host "✅ Docker image pushed successfully to: $ImageTag" -ForegroundColor Green
}

# 4. Provision Azure Infrastructure
Write-Host "`n[3/6] Provisioning Azure Resource Group ($ResourceGroup in $Location)..." -ForegroundColor Yellow
az group create --name $ResourceGroup --location $Location --output none

$AcaEnv = "cae-linkedin-bot"
$FileShare = "botdata"
# Storage account names must be lowercase alphanumeric, max 24 chars
$randomSuffix = (Get-Random -Minimum 1000 -Maximum 9999)
$StorageAccount = "stlinkedinbot$randomSuffix"

Write-Host "Creating Azure Storage Account ($StorageAccount) for persistent state..." -ForegroundColor Yellow
az storage account create `
    --name $StorageAccount `
    --resource-group $ResourceGroup `
    --location $Location `
    --sku Standard_LRS `
    --kind StorageV2 `
    --output none

$StorageKey = az storage account keys list `
    --resource-group $ResourceGroup `
    --account-name $StorageAccount `
    --query "[0].value" `
    --output tsv

Write-Host "Creating Azure File Share ($FileShare)..." -ForegroundColor Yellow
az storage share-rm create `
    --resource-group $ResourceGroup `
    --storage-account $StorageAccount `
    --name $FileShare `
    --quota 5 `
    --output none

Write-Host "`n[4/6] Creating Azure Container Apps Environment ($AcaEnv)..." -ForegroundColor Yellow
az containerapp env create `
    --name $AcaEnv `
    --resource-group $ResourceGroup `
    --location $Location `
    --output none

Write-Host "Mounting Azure File Share to ACA Environment..." -ForegroundColor Yellow
az containerapp env storage set `
    --name $AcaEnv `
    --resource-group $ResourceGroup `
    --storage-name botstorage `
    --azure-file-account-name $StorageAccount `
    --azure-file-account-key $StorageKey `
    --azure-file-share-name $FileShare `
    --access-mode ReadWrite `
    --output none

# 5. Parse .env file for environment variables and secrets
Write-Host "`n[5/6] Parsing environment variables from .env..." -ForegroundColor Yellow
$envPath = Join-Path (Get-Location) ".env"
if (-not (Test-Path $envPath)) {
    Write-Error "Local .env file not found at $envPath"
}

$envVarsList = @()
$secretsList = @()

Get-Content $envPath | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $val = $parts[1].Trim().Trim('"').Trim("'")

        if ($key -and $val) {
            # Convert keys to lowercase alphanumeric for Azure secret naming convention
            $secretKeyName = ($key.ToLower() -replace "_", "-")
            $secretsList += "$secretKeyName=$val"
            $envVarsList += "$key=secretref:$secretKeyName"
        }
    }
}

# 6. Deploy Container App
Write-Host "`n[6/6] Deploying Azure Container App ($AppName)..." -ForegroundColor Yellow

$secretsArg = $secretsList -join " "
$envVarsArg = $envVarsList -join " "

# Check if container app already exists
$existingApp = az containerapp show --name $AppName --resource-group $ResourceGroup --output json 2>$null

if ($existingApp) {
    Write-Host "Updating existing container app revision..." -ForegroundColor Yellow
    az containerapp update `
        --name $AppName `
        --resource-group $ResourceGroup `
        --image "docker.io/$ImageTag" `
        --output none
} else {
    Write-Host "Creating new container app..." -ForegroundColor Yellow
    az containerapp create `
        --name $AppName `
        --resource-group $ResourceGroup `
        --environment $AcaEnv `
        --image "docker.io/$ImageTag" `
        --min-replicas 1 `
        --max-replicas 1 `
        --ingress disabled `
        --cpu 0.25 `
        --memory 0.5Gi `
        --secrets $secretsList `
        --env-vars $envVarsList `
        --output none
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "• Resource Group: $ResourceGroup"
Write-Host "• Container App:  $AppName"
Write-Host "• Environment:    $AcaEnv"
Write-Host "• Persistent Storage: Azure Files ($FileShare) mounted at /app/data"
Write-Host "`n👉 To view live logs from your running bot:" -ForegroundColor Cyan
Write-Host "az containerapp logs show --name $AppName --resource-group $ResourceGroup --follow" -ForegroundColor White
Write-Host "`n👉 To check container status:" -ForegroundColor Cyan
Write-Host "az containerapp show --name $AppName --resource-group $ResourceGroup --query ""properties.runningStatus""" -ForegroundColor White
