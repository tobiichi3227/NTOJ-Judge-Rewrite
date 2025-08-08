#include <fstream>
#include <string>

using namespace std;

// from https://github.com/TIOJ-INFOR-Online-Judge/tioj-judge/blob/main/tools/default-scoring.cpp
bool LineCompare(std::ifstream& f_ans, std::ifstream& f_usr) {
  constexpr char kWhites[] = " \n\r\t";
  for (; f_ans.eof() == f_usr.eof();) {
    if (f_ans.eof()) return true;
    std::string s, t;
    getline(f_ans, s);
    getline(f_usr, t);
    s.erase(s.find_last_not_of(kWhites) + 1);
    t.erase(t.find_last_not_of(kWhites) + 1);
    if (s != t) {
      return false;
    }
  }
  while (!f_ans.eof() || !f_usr.eof()) {
    std::string s;
    if (!f_ans.eof()) {
      getline(f_ans, s);
    } else {
      getline(f_usr, s);
    }
    if (s.find_last_not_of(kWhites) != std::string::npos) {
      return false;
    }
  }
  return true;
}

int main(int argc, char *argv[]) {
    std::ifstream test_out(argv[2]), user_ans(argv[3]);
    return !LineCompare(test_out, user_ans);
}
