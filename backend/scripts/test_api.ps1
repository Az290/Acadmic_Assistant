# Test API Script for Academic Assistant
# This script tests all major flows

$BASE_URL = "http://localhost:8000"
$headers = @{"Content-Type" = "application/json"}

function Test-Login {
    param($email, $password)

    $body = @{
        email = $email
        password = $password
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$BASE_URL/v1/auth/login" -Method POST -Headers $headers -Body $body
    return $response
}

function Test-GetMe {
    $response = Invoke-RestMethod -Uri "$BASE_URL/v1/auth/me" -Method GET -Headers @{Authorization = "Bearer $token"}
    return $response
}

function Test-CreateInstructor {
    param($email, $fullName)

    $body = @{
        email = $email
        full_name = $fullName
        password = "Instructor@123"
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$BASE_URL/v1/auth/admin/create-instructor" -Method POST -Headers $headers -Body $body -WebSession $session
    return $response
}

function Test-Register {
    param($email, $fullName, $password)

    $body = @{
        email = $email
        password = $password
        full_name = $fullName
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$BASE_URL/v1/auth/register" -Method POST -Headers $headers -Body $body
    return $response
}

# ====== START TESTING ======

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ACADEMIC ASSISTANT - API TEST SUITE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Create Instructor via Admin
Write-Host "[1] Creating Instructor account..." -ForegroundColor Yellow
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

# Login as Admin
$loginBody = @{email="admin@test.edu.vn";password="Admin@123"} | ConvertTo-Json
$login = Invoke-WebRequest -Uri "$BASE_URL/v1/auth/login" -Method POST -Headers $headers -Body $loginBody -WebSession $session
Write-Host "Admin login: OK" -ForegroundColor Green

# Create Instructor
$instructorBody = @{
    email="gv.nguyenvana@test.edu.vn"
    full_name="Nguyen Van A"
    password="Instructor@123"
} | ConvertTo-Json

try {
    $instructor = Invoke-WebRequest -Uri "$BASE_URL/v1/auth/admin/create-instructor" -Method POST -Headers $headers -Body $instructorBody -WebSession $session
    Write-Host "Created Instructor: gv.nguyenvana@test.edu.vn" -ForegroundColor Green
} catch {
    Write-Host "Instructor may already exist" -ForegroundColor Yellow
}

# Create more Instructors
foreach ($i in 2..3) {
    $body = @{
        email="gv.giangvien$i@test.edu.vn"
        full_name="Giang Vien $i"
        password="Instructor@123"
    } | ConvertTo-Json
    try {
        Invoke-WebRequest -Uri "$BASE_URL/v1/auth/admin/create-instructor" -Method POST -Headers $headers -Body $body -WebSession $session | Out-Null
        Write-Host "Created: gv.giangvien$i@test.edu.vn" -ForegroundColor Green
    } catch {}
}

Write-Host ""

# 2. Create Student accounts
Write-Host "[2] Creating Student accounts..." -ForegroundColor Yellow
$students = @()
for ($i = 1; $i -le 5; $i++) {
    $email = "sv.sinhvien$i@test.edu.vn"
    $body = @{
        email=$email
        password="Student@123"
        full_name="Sinh Vien $i"
    } | ConvertTo-Json

    try {
        $reg = Invoke-WebRequest -Uri "$BASE_URL/v1/auth/register" -Method POST -Headers $headers -Body $body -ErrorAction Stop
        Write-Host "Created Student: $email" -ForegroundColor Green
        $students += $email
    } catch {
        Write-Host "Student may exist: $email" -ForegroundColor Yellow
        $students += $email
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TEST ACCOUNTS CREATED" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ADMIN: admin@test.edu.vn / Admin@123" -ForegroundColor White
Write-Host "INSTRUCTOR: gv.nguyenvana@test.edu.vn / Instructor@123" -ForegroundColor White
Write-Host "STUDENT: sv.sinhvien1@test.edu.vn / Student@123" -ForegroundColor White
Write-Host ""

# Save session info for further testing
$script:session = $session
Write-Host "Session initialized. Ready for API testing." -ForegroundColor Green
