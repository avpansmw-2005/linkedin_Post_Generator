<#
.SYNOPSIS
    Generates Azure Service Principal credentials for GitHub Actions CI/CD to Azure Container Apps.

.DESCRIPTION
    Creates an Azure Active Directory Service Principal with Contributor permissions on the
    target resource group (rg-linkedin-bot) and outputs the JSON needed for GitHub Secrets.
#>

param (
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "rg-linkedin-bot",

    [Parameter(Mandatory=$false)]
    [string]$SpName = "sp-aca-linkedin-bot"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🔑 GitHub Actions Azure Setup Helper" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verify Azure CLI login
Write-Host "`n[1/3] Checking Azure CLI authentication..." -ForegroundColor Yellow
$azAccount = az account show --output json 2>$null | ConvertFrom-Json
if (-not $azAccount) {
    Write-Host "Please log in to Azure CLI..." -ForegroundColor Yellow
    az login
    $azAccount = az account show --output json | ConvertFrom-Json
}
$subId = $azAccount.id
Write-Host "✅ Logged in as: $($azAccount.user.name) (Subscription ID: $subId)" -ForegroundColor Green

# 2. Create Service Principal
Write-Host "`n[2/3] Creating Azure Service Principal for GitHub Actions..." -ForegroundColor Yellow
$scope = "/subscriptions/$subId/resourceGroups/$ResourceGroup"

$spJson = az ad sp create-for-rbac `
    --name $SpName `
    --role "Contributor" `
    --scopes $scope `
    --sdk-auth `
    --output json

if (-not $spJson) {
    Write-Error "Failed to generate Service Principal."
}

Write-Host "✅ Service Principal created successfully!" -ForegroundColor Green

# 3. Print instructions for GitHub Secrets
Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "📋 NEXT STEPS: Add Secrets in GitHub" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Go to your GitHub repository:" -ForegroundColor White
Write-Host "https://github.com/avpansmw-2005/linkedin_Post_Generator/settings/secrets/actions" -ForegroundColor Yellow
Write-Host "`nAdd the following 3 Repository Secrets:" -ForegroundColor White
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "1. Secret Name: AZURE_CREDENTIALS" -ForegroundColor Green
Write-Host "   Secret Value (Copy and paste the entire JSON below):" -ForegroundColor White
Write-Host $spJson -ForegroundColor Magenta
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "2. Secret Name: DOCKERHUB_USERNAME" -ForegroundColor Green
Write-Host "   Secret Value: avneetpandey82" -ForegroundColor White
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "3. Secret Name: DOCKERHUB_TOKEN" -ForegroundColor Green
Write-Host "   Secret Value: (Your Docker Hub Personal Access Token from https://hub.docker.com/settings/security)" -ForegroundColor White
Write-Host "==========================================================`n" -ForegroundColor Cyan
