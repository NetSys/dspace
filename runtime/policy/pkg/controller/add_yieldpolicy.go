package controller

import (
	"digi.dev/digivice/runtime/policy/pkg/controller/yieldpolicy"
)

func init() {
	// AddToManagerFuncs is a list of functions to create controllers and add them to a manager.
	AddToManagerFuncs = append(AddToManagerFuncs, yieldpolicy.Add)
}
