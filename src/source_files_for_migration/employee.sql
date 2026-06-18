REPLACE PROCEDURE sp_GetEmployeeBonus
(
    IN  pi_EmpID      INTEGER, 
    OUT po_EmpName    VARCHAR(50),
    INOUT pio_Bonus   DECIMAL(10,2)
)
-- This defines the label for the procedure block
MAIN_BLOCK: 
BEGIN
    -- Declare local variables
    DECLARE v_Salary DECIMAL(10,2);
    DECLARE v_Dept   VARCHAR(50);

    -- Declare a custom exception/handler for missing data
    DECLARE EXIT HANDLER FOR NOT FOUND
    BEGIN
        SET po_EmpName = 'Unknown Employee';
        SET pio_Bonus = 0.00;
    END;

    -- Retrieve Employee Details and Salary
    SELECT EmpName, Department, Salary 
    INTO po_EmpName, v_Dept, v_Salary
    FROM EmployeeTable
    WHERE EmpID = pi_EmpID;

    -- Apply business logic: double the bonus if they are in 'Sales'
    IF v_Dept = 'Sales' THEN
        SET pio_Bonus = pio_Bonus * 2;
    END IF;

    -- Optional Logging or Update
    INSERT INTO BonusAuditLog (EmpID, EmpName, BonusAmount, LogDate)
    VALUES (pi_EmpID, po_EmpName, pio_Bonus, CURRENT_TIMESTAMP);

END MAIN_BLOCK;
