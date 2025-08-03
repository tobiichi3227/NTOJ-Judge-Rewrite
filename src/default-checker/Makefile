CXX := c++
CXXFLAGS := -O2 -std=c++17

SRCS := lcmp.cpp fcmp.cpp rcmp4.cpp rcmp6.cpp rcmp9.cpp
BINS := $(SRCS:.cpp=)

all: $(BINS)

%: %.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f $(BINS)

