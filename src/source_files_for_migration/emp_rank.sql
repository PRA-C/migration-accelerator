-- TERADATA QUERY
SELECT 
    EmpID,
    EmpName,
    Department,
    Salary,
    RANK() OVER (PARTITION BY Department ORDER BY Salary DESC) AS SalaryRank,
    ROW_NUMBER() OVER (PARTITION BY Department ORDER BY HireDate) AS TenureRank,
    AVG(Salary) OVER (PARTITION BY Department) AS DeptAvgSalary,
    Salary - AVG(Salary) OVER (PARTITION BY Department) AS SalaryVsAvg
FROM EmployeeTable
WHERE ActiveFlag = 'Y'
    AND HireDate >= CURRENT_DATE - INTERVAL '5' YEAR
QUALIFY SalaryRank <= 5  -- Teradata QUALIFY (Top 5 earners per dept)
    AND TenureRank <= 10
ORDER BY Department, SalaryRank;